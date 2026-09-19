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
            text: "RTX 3080 Ti FE - NVAPI"
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            color: "#cccccc"
            font.pixelSize: 15
            text: "Lancez Lancer-pont.cmd, puis activez RTX 3080 Ti FE dans Appareils. Le Canvas controle une zone RGBW et la luminosite de la zone monochrome. OpenRGB peut rester ferme."
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            color: "#cccccc"
            font.pixelSize: 15
            text: "Le pont local doit rester actif. Ses journaux se trouvent dans %LOCALAPPDATA%/NvidiaFeBridge. Arreter-pont.cmd restaure l'etat initial. Cette page permet de retrouver le controleur; elle ne confirme pas l'etat du pont."
            wrapMode: Text.WordWrap
        }
        Button {
            text: "Rechercher le controleur local"
            onClicked: discovery.Refresh()
        }
    }
}
