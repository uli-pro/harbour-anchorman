import QtQuick 2.0

// Ends listening after some minutes, fading out over the last 20 seconds,
// or at the end of the chapter. Knows only the player, so any page that
// plays can use it. The page pauses on expired(); pausing by hand turns
// the timer off (cancel()).
Item {
    id: timer

    property var player
    // "off", "minutes" or "chapter"
    property string mode: "off"
    property int minutes: 0
    // In ms since 1970: the time left comes from the clock, so a late tick
    // with the screen off does not put the end back.
    property double endTime: 0
    property double remaining: 0
    readonly property int fade: 20000

    signal expired()

    function setMinutes(n) {
        mode = "minutes"
        minutes = n
        endTime = Date.now() + n * 60000
        remaining = endTime - Date.now()
        player.holdAtChapterEnd = false
        player.volume = 1
    }

    function setChapterEnd() {
        mode = "chapter"
        player.holdAtChapterEnd = true
        loud()
    }

    function cancel() {
        mode = "off"
        player.holdAtChapterEnd = false
        loud()
    }

    // While playing at once; paused only when playing again, or the end of
    // a pause just asked for might be heard loud.
    function loud() {
        if (player.playing)
            player.volume = 1
    }

    function tick() {
        remaining = endTime - Date.now()
        if (remaining > 0) {
            player.volume = Math.min(1, remaining / fade)
            return
        }
        mode = "off"
        player.volume = 0
        expired()
    }

    Timer {
        running: timer.mode === "minutes"
        repeat: true
        // Small steps while fading.
        interval: timer.remaining <= timer.fade + 1000 ? 200 : 1000
        onTriggered: timer.tick()
    }

    Connections {
        target: player
        onHeld: {
            if (timer.mode === "chapter") {
                timer.mode = "off"
                timer.expired()
            }
        }
        // Before the sound: playing is set before the audio starts.
        onPlayingChanged: {
            if (player.playing && timer.mode !== "minutes")
                player.volume = 1
        }
    }
}
