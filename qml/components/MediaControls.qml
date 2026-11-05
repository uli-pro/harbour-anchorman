import QtQuick 2.0
import Amber.Mpris 1.0

// Controls on the lock screen, in the notifications and on headphones,
// for the open book. The Audio permission lets the app own the name.
MprisPlayer {
    readonly property var reader: app.reader

    // The lock screen shows these as rich text, outside the sandbox; a tag
    // in a book's title could load an image from the net.
    function plain(text) {
        return String(text).replace(/</g, "\u2039")
    }

    serviceName: "anchorman"
    identity: "Anchorman"
    desktopEntry: "harbour-anchorman"

    // Fixed: Amber does not pass a later change of CanControl on, and false
    // also turns off CanPlay and CanPause (seen on the device).
    canControl: true
    canPlay: reader !== null && reader.hasAudio
    canPause: reader !== null && reader.hasAudio
    canGoNext: reader !== null && reader.hasAudio
    canGoPrevious: reader !== null && reader.hasAudio
    // The narration is a sequence of sentences across several files, not
    // one track with a position.
    canSeek: false
    playbackStatus: reader === null ? Mpris.Stopped
                  : reader.playing ? Mpris.Playing : Mpris.Paused

    metaData {
        title: reader !== null ? plain(reader.book.title) : ""
        // A list would be shown as "A,B".
        contributingArtist: reader !== null ? [plain(reader.book.authors.join("; "))] : []
        artUrl: reader !== null ? reader.coverUrl : ""
    }

    onPlayRequested: if (reader) reader.play()
    // A stop that forgot the place would help nobody listening to a book.
    onPauseRequested: if (reader) reader.pause()
    onStopRequested: if (reader) reader.pause()
    onPlayPauseRequested: {
        if (!reader)
            return
        if (reader.playing)
            reader.pause()
        else
            reader.play()
    }
    onNextRequested: if (reader) reader.nextSentence()
    onPreviousRequested: if (reader) reader.previousSentence()
}
