import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(r"e:\ascend media rpc production\Stremio-Ascend\vencord_installer")
from vencord_installer_gui import InstallerApp, DISCORD_TARGETS, local_app_data

class HeadlessApp(InstallerApp):
    def __init__(self):
        self.target_vars = {}
        class DummyVar:
            def __init__(self, val):
                self.val = val
            def get(self):
                return self.val
            def strip(self):
                return str(self.val).strip()

        self.close_discord = DummyVar(True)
        self.skip_update = DummyVar(False)
        self.custom_path = DummyVar("")
        
        for key in DISCORD_TARGETS:
            self.target_vars[key] = DummyVar(key == "canary")

    def _log(self, msg, tag="info"):
        print(f"[{tag.upper()}] {msg}")

    def _set_status(self, msg, prog=None):
        print(f"[STATUS {prog}%] {msg}")

if __name__ == "__main__":
    app = HeadlessApp()
    app.install()
