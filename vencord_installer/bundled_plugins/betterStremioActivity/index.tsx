/*
 * Vencord, a Discord client mod
 * Copyright (c) 2024 Vendicated and contributors
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

import { getUserSettingLazy } from "@api/UserSettings";
import { definePluginSettings } from "@api/Settings";
import { Button } from "@components/Button";
import { ErrorCard } from "@components/ErrorCard";
import { Flex } from "@components/Flex";
import { Heading } from "@components/Heading";
import { Link } from "@components/Link";
import { Paragraph } from "@components/Paragraph";
import { Margins } from "@utils/margins";
import { classes } from "@utils/misc";
import definePlugin, { OptionType } from "@utils/types";
import { React } from "@webpack/common";


const ShowCurrentGame = getUserSettingLazy<boolean>("status", "showCurrentGame")!;
const STREMIO_ACTIVITY_NAME = "Stremio";
const YOUTUBE_WATCH_TOGETHER_APPLICATION_ID = "880218394199220334";

const activityTargets = {
    stremio: {
        applicationId: undefined,
    },
    youtubeWatchTogether: {
        applicationId: YOUTUBE_WATCH_TOGETHER_APPLICATION_ID,
    },
} as const;

const settings = definePluginSettings({
    activityTarget: {
        type: OptionType.SELECT,
        description: "Choose which app BetterStremioActivity spoofs while keeping the Stremio resolver fields.",
        options: [
            { label: "Stremio", value: "stremio", default: true },
            { label: "YouTube Watch Together", value: "youtubeWatchTogether" },
        ],
    },
});

function spoofActivityTarget(activity: any) {
    const target = activityTargets[settings.store.activityTarget ?? "stremio"];

    if (target.applicationId) {
        activity.application_id = target.applicationId;
        activity.applicationId = target.applicationId;
    }
}


export default definePlugin({
    name: "BetterStremioActivity",
    description: "Replaces Stremio's RPC activity with the current movie/series name and can spoof it as YouTube Watch Together.",
    authors: [{ name: "Loukious", id: 0n }],
    settings,

    flux: {
        LOCAL_ACTIVITY_UPDATE(data: { activity: any; socketId: string; }) {
            const activity = data?.activity;
            if (!activity || activity.name !== STREMIO_ACTIVITY_NAME) return;

            spoofActivityTarget(activity);

            if (
                activity.timestamps?.end ||
                activity.state?.toLowerCase().includes("paused") ||
                activity.assets?.small_text?.toLowerCase().includes("paused")
            ) {
                activity.name = activity.details;

                if (activity.state) {
                    activity.details = activity.state;
                }

                if (activity.assets?.small_text) {
                    activity.state = activity.assets.small_text;
                }
            }
        },
    },

    settingsAboutComponent: () => {
        const gameActivityEnabled = ShowCurrentGame.useSetting();

        return (
            <>
                {!gameActivityEnabled && (
                    <ErrorCard
                        className={classes(Margins.top16, Margins.bottom16)}
                        style={{ padding: "1em" }}
                    >
                        <Heading>Notice</Heading>
                        <Paragraph>Activity Sharing isn't enabled, people won't be able to see your custom rich presence!</Paragraph>

                        <Button
                            variant="secondary"
                            className={Margins.top8}
                            onClick={() => ShowCurrentGame.updateSetting(true)}
                        >
                            Enable
                        </Button>
                    </ErrorCard>
                )}

                <Flex flexDirection="column" style={{ display: "flex", flexDirection: "column", gap: "1em", fontSize: "15px", lineHeight: "1.6" }} className={Margins.top16}>
                    <Paragraph>
                        For this to work you will need <Link href="https://github.com/Loukious/stremio-shell-ng">this Stremio fork</Link>
                    </Paragraph>
                    <Paragraph>
                        After installing the fork, simply enable this plugin and it will automatically replace the Stremio activity with the current movie/series name.
                    </Paragraph>
                </Flex>

            </>
        );
    }

});
