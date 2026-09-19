import QtQuick
import QtQuick.Controls

Item {
    anchors.fill: parent
    Column {
        x: 12
        y: 12
        width: parent.width - 24
        spacing: 14
        Text {
            width: parent.width
            color: "white"
            font.pixelSize: 22
            text: "Stream Deck Background"
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            color: "#cccccc"
            font.pixelSize: 15
            text: "Lancez Demarrer-StreamDeck.cmd, puis activez Stream Deck MK.2 Background dans Appareils. Le canvas SignalRGB pilote les quinze fonds sans remplacer les icones ou les actions."
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            color: "#cccccc"
            font.pixelSize: 15
            text: "Le pont local doit rester ouvert. Ses journaux et son etat se trouvent dans %LOCALAPPDATA%/CodexLocalBridges/StreamDeck/runtime. Le premier rendu naturel peut prendre une minute."
            wrapMode: Text.WordWrap
        }
        Button {
            text: "Rechercher le controleur local"
            onClicked: discovery.Refresh()
        }
    }
}
