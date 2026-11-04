import QtQuick 2.0
import QtMultimedia 5.6

// Plays the clips of one chapter, one sentence after the other, and tells
// which sentence is spoken. The page hands over the next chapter when this
// one is finished.
//
// The audio file runs on from clip to clip; it is only sought when a clip
// does not follow the previous one. A timer is set to the end of the clip
// instead of polling the position.
Item {
    id: player

    // Folder of the unpacked book; clips name their audio file within it.
    property string root
    property real rate: 1.0
    property int chapter: -1
    // [{id, audio, begin, end}], times in ms, end null = to the end of the file
    property var clips: []
    property int index: -1
    // Times within the current clip at which marked(n) is sent, ascending.
    property var marks: []
    // What the user asked for; the audio itself stops briefly whenever a
    // file is loaded.
    property bool playing: false
    readonly property bool active: index >= 0
    // Guarded: clips and index change one after the other.
    readonly property string currentId: index >= 0 && index < clips.length ? clips[index].id : ""

    signal sentence(int chapter, int index)
    signal finished(int chapter)
    signal marked(int n)
    signal failed()

    property string loadedPath: ""
    property int pendingSeek: -1
    property int nextMark: 0
    property real loadedRate: 1.0
    // The chapter is finished and the page has not yet handed over the next.
    property bool waiting: false
    // Set by next() at the end of a chapter: the rest of the clip is not
    // played, so the next chapter is sought even if it follows on.
    property bool skipping: false

    // In ms within the audio file; read when needed, the property binding
    // of Audio is only updated once a second.
    function currentPosition() {
        return audio.position
    }

    function fileUrl(path) {
        return "file://" + (root + "/" + path).split("/").map(encodeURIComponent).join("/")
    }

    // Seeks are dropped until the file reports seekable, and a playback rate
    // only takes effect when a file is loaded (measured on the device).
    function load(path, ms, reload) {
        if (path === loadedPath && !reload && pendingSeek < 0 && audio.seekable) {
            audio.seek(ms)
        } else {
            pendingSeek = ms
            if (path !== loadedPath || reload) {
                loadedPath = path
                audio.source = ""
                audio.playbackRate = rate
                loadedRate = rate
                audio.source = fileUrl(path)
            }
        }
        if (playing)
            audio.play()
    }

    function start(chapterIndex, list, i, offset) {
        chapter = chapterIndex
        clips = list
        playing = true
        jump(i, offset || 0)
    }

    // Goes on with the next chapter where the last clip ended.
    function continueWith(chapterIndex, list) {
        var last = clips[clips.length - 1]
        var seek = skipping || !follows(last, list[0])
        waiting = false
        skipping = false
        chapter = chapterIndex
        clips = list
        index = 0
        resetMarks()
        if (seek)
            load(list[0].audio, list[0].begin)
        sentence(chapter, 0)
        arm()
    }

    function jump(i, offset) {
        waiting = false
        skipping = false
        index = i
        resetMarks()
        load(clips[i].audio, clips[i].begin + (offset || 0))
        sentence(chapter, index)
        arm()
    }

    function pause() {
        playing = false
        alarm.stop()
        audio.pause()
    }

    function resume() {
        if (index < 0)
            return
        playing = true
        if (loadedRate !== rate)
            load(loadedPath, pendingSeek >= 0 ? pendingSeek : audio.position, true)
        audio.play()
        arm()
    }

    function stop() {
        playing = false
        alarm.stop()
        audio.stop()
        index = -1
        clips = []
        chapter = -1
        pendingSeek = -1
        waiting = false
        skipping = false
        resetMarks()
    }

    // Back to the start of the sentence, or to the previous one right after
    // a sentence began, as in music players. Not across chapters.
    function previous() {
        if (index < 0)
            return
        var early = audio.position - clips[index].begin < 1500 * rate
        jump(early && index > 0 ? index - 1 : index)
    }

    function next() {
        if (index < 0)
            return
        if (index + 1 < clips.length) {
            jump(index + 1)
        } else if (!waiting) {
            alarm.stop()
            skipping = true
            waiting = true
            finished(chapter)
        }
    }

    function setMarks(list) {
        marks = list
        nextMark = 0
        arm()
    }

    function resetMarks() {
        marks = []
        nextMark = 0
    }

    // Storyteller leaves no gaps; small ones of other tools are played,
    // larger ones hold audio without text and are skipped.
    function follows(a, b) {
        return a.audio === b.audio && a.end !== null
                && b.begin >= a.end && b.begin - a.end <= 500
    }

    function arm() {
        alarm.stop()
        if (!playing || index < 0 || pendingSeek >= 0 || waiting)
            return
        var target = nextMark < marks.length ? marks[nextMark] : clips[index].end
        if (target === null)
            return  // the end of the file ends the clip
        alarm.interval = Math.max(10, (target - audio.position) / audio.playbackRate)
        alarm.start()
    }

    function check() {
        var pos = audio.position
        if (nextMark < marks.length) {
            if (pos >= marks[nextMark] - 15)
                marked(nextMark++)
            arm()
        } else if (clips[index].end !== null && pos >= clips[index].end - 15) {
            advance()
        } else {
            arm()
        }
    }

    function advance() {
        if (waiting)
            return  // also the end of the file may still report
        if (index + 1 >= clips.length) {
            alarm.stop()
            waiting = true
            finished(chapter)
            return
        }
        var previousClip = clips[index]
        index++
        resetMarks()
        if (!follows(previousClip, clips[index]))
            load(clips[index].audio, clips[index].begin)
        sentence(chapter, index)
        arm()
    }

    // While paused the new rate is taken up by resume().
    onRateChanged: {
        if (playing && index >= 0)
            load(loadedPath, pendingSeek >= 0 ? pendingSeek : audio.position, true)
    }

    Audio {
        id: audio

        onSeekableChanged: {
            if (seekable && player.pendingSeek >= 0) {
                seek(player.pendingSeek)
                player.pendingSeek = -1
                player.arm()
            }
        }
        onStatusChanged: {
            if (status === Audio.EndOfMedia && player.playing && player.index >= 0
                    && player.pendingSeek < 0)
                player.advance()
        }
        onError: {
            console.warn("Audio error", error, errorString, source)
            player.stop()
            player.failed()
        }
    }

    Timer {
        id: alarm
        onTriggered: player.check()
    }
}
