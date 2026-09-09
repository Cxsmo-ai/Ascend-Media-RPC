const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_DIR = path.join(__dirname, 'BetterVencordPatchset');
const PLUGINS_FILE = path.join(__dirname, 'plugins.txt');
const EQUICORD_DIR = path.join(REPO_DIR, 'dist', 'Equicord');
const PLUGIN_DIR = path.join(EQUICORD_DIR, 'src', 'userplugins');
const BUNDLED_PLUGINS_DIR = path.join(__dirname, 'bundled_plugins');

function log(msg) {
    console.log(`[VERIFY] ${msg}`);
}

function run(cmd, cwd = REPO_DIR) {
    log(`Running: ${cmd} in ${cwd}`);
    try {
        return execSync(cmd, { cwd, stdio: 'inherit', encoding: 'utf-8' });
    } catch (e) {
        log(`Error running: ${cmd}`);
        throw e;
    }
}

function parsePlugins() {
    log('Parsing plugins from plugins.txt...');
    if (!fs.existsSync(PLUGINS_FILE)) return [];
    return fs.readFileSync(PLUGINS_FILE, 'utf-8')
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'));
}

function setupPlugins(urls) {
    if (!fs.existsSync(PLUGIN_DIR)) {
        fs.mkdirSync(PLUGIN_DIR, { recursive: true });
    }

    const bundledBetterStremio = path.join(BUNDLED_PLUGINS_DIR, 'betterStremioActivity');
    const betterStremioTarget = path.join(PLUGIN_DIR, 'betterStremioActivity');
    if (fs.existsSync(bundledBetterStremio)) {
        fs.cpSync(bundledBetterStremio, betterStremioTarget, { recursive: true });
        log('Synced bundled BetterStremioActivity.');
    }

    const pluginNames = [];
    urls.forEach(url => {
        const name = url.split('/').pop().replace('.git', '');
        const target = path.join(PLUGIN_DIR, name);
        pluginNames.push(name);

        if (fs.existsSync(target)) {
            log(`Updating ${name}...`);
            try {
                execSync('git pull', { cwd: target, stdio: 'ignore' });
            } catch (e) {
                log(`Failed to update ${name}, skipping update.`);
            }
        } else {
            log(`Cloning ${name}...`);
            try {
                execSync(`git clone ${url} ${name}`, { cwd: PLUGIN_DIR, stdio: 'ignore' });
            } catch (e) {
                log(`Failed to clone ${name}, removing.`);
                if (fs.existsSync(target)) fs.rmSync(target, { recursive: true, force: true });
            }
        }
    });
    return pluginNames;
}

function getGitInfo(cwd) {
    try {
        const hash = execSync('git rev-parse --short HEAD', { cwd, stdio: 'pipe' }).toString().trim();
        const remoteRaw = execSync('git remote get-url origin', { cwd, stdio: 'pipe' }).toString().trim();
        const remote = remoteRaw
            .replace("https://github.com/", "")
            .replace("git@github.com:", "")
            .replace(/.git$/, "");
        return { hash, remote };
    } catch (e) {
        return { hash: 'unknown', remote: 'unknown' };
    }
}

function tryBuild(env) {
    try {
        execSync('pnpm build', { cwd: EQUICORD_DIR, stdio: 'pipe', encoding: 'utf-8', env: { ...process.env, ...env } });
        return { success: true };
    } catch (e) {
        return { success: false, error: e.stdout + e.stderr };
    }
}

async function main() {
    try {
        // 1. Update Patchset
        log('Updating BetterVencordPatchset...');
        run('git pull');
        run('git submodule update --init --recursive');
        run('pnpm install');
        run('pnpm dlx tsx scripts/build.ts --equicord');

        // 2. Setup Plugins
        const urls = parsePlugins();
        let pluginNames = setupPlugins(urls);

        // 3. Build Equicord Dependencies
        log('Installing Equicord dependencies...');
        run('pnpm install', EQUICORD_DIR);

        // 4. Prepare Environment Variables
        log('Preparing build environment variables...');
        const builderInfo = getGitInfo(REPO_DIR);
        const baseInfo = getGitInfo(path.join(REPO_DIR, 'base', 'Equicord'));
        const buildEnv = {
            VENCORD_HASH: `${baseInfo.hash} (BetterVencord patchset built by ${builderInfo.hash})`,
            EQUICORD_HASH: `${baseInfo.hash} (BetterVencord patchset built by ${builderInfo.hash})`,
            BV_REMOTE: builderInfo.remote
        };

        // 5. Iterative build
        log('Starting iterative build process...');
        let allSuccessful = false;
        const brokenPlugins = [];

        while (!allSuccessful) {
            log(`Attempting build with ${pluginNames.length} plugins...`);
            const result = tryBuild(buildEnv);
            if (result.success) {
                log('Build successful!');
                allSuccessful = true;
            } else {
                log('Build failed. Identifying broken plugin...');
                // ... identifies broken plugin ...
                let foundBroken = false;
                for (const name of pluginNames) {
                    if (result.error.includes(name)) {
                        log(`Found error related to plugin: ${name}`);
                        const target = path.join(PLUGIN_DIR, name);
                        fs.rmSync(target, { recursive: true, force: true });
                        brokenPlugins.push(name);
                        pluginNames = pluginNames.filter(p => p !== name);
                        foundBroken = true;
                        break;
                    }
                }

                if (!foundBroken) {
                    log('Could not identify broken plugin from error log. Testing plugins one by one...');
                    for (const name of [...pluginNames]) {
                        log(`Testing without plugin: ${name}`);
                        const target = path.join(PLUGIN_DIR, name);
                        const backup = path.join(EQUICORD_DIR, 'src', 'temp_plugin_backup');
                        if (!fs.existsSync(backup)) fs.mkdirSync(backup, { recursive: true });
                        const backupPath = path.join(backup, name);
                        
                        fs.renameSync(target, backupPath);

                        const testResult = tryBuild(buildEnv);
                        if (testResult.success) {
                            log(`Identified broken plugin: ${name}`);
                            brokenPlugins.push(name);
                            pluginNames = pluginNames.filter(p => p !== name);
                            fs.rmSync(backupPath, { recursive: true, force: true });
                            foundBroken = true;
                            // Now that we found one, we continue the while loop to see if the build succeeds with the rest
                            break; 
                        } else {
                            // Put it back
                            fs.renameSync(backupPath, target);
                        }
                    }
                }
                
                if (!foundBroken) {
                    log('CRITICAL: Could not find broken plugin even by removing them one by one. Build might be broken fundamentally.');
                    break;
                }
            }
        }

        log('Final Plugin Results:');
        log(`Working Plugins: ${pluginNames.join(', ')}`);
        log(`Broken Plugins: ${brokenPlugins.join(', ')}`);

        if (allSuccessful) {
            log('Injecting into Discord Canary...');
            run('pnpm inject canary', EQUICORD_DIR);
            log('Verification and installation complete!');
        }

    } catch (e) {
        console.error(e);
    }
}

main();
