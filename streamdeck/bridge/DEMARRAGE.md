# Utilisation quotidienne

Conserver ce dossier à un emplacement fixe. Stream Deck **7.5.1.22901** doit être ouvert, avec le MK.2 à quinze touches. Le pilote SignalRGB qui écrit directement les images USB du Stream Deck doit rester désactivé ; le client réseau livré ici anime le fond et conserve les actions et les icônes.

1. Double-cliquer **Demarrer-StreamDeck.cmd**. Au premier lancement, il crée `.venv` avec Python 3.10+ x64 disponible dans PATH et installe `frida==17.18.0` et `Pillow==12.3.0`. Il prépare le client SignalRGB de la session puis continue en arrière-plan, sans limite d’une heure.
2. Pour terminer, double-cliquer **Arreter-StreamDeck.cmd**. Il demande la restauration, attend le déchargement normal et rend le client SignalRGB inerte. Ne pas arrêter le processus Python de force.

Ces lanceurs seuls n’enregistrent pas de démarrage automatique Windows ; le superviseur du dépôt parent le gère lorsqu’il est configuré. Sans ce superviseur, relancer le pont après une fermeture ou un redémarrage de Stream Deck. Une version différente de l’application est refusée. Le premier rendu naturel peut demander une minute si une horloge attend son prochain tick. Voir [la procédure de mise à jour Elgato](../UPDATE-ELGATO.md).

Le lanceur choisit le dossier OneDrive déjà confirmé sur cette machine. Pour un autre emplacement :

```powershell
.\Start-Bridge.ps1 -SignalRGBPluginDirectory 'C:\chemin\WhirlwindFX\Plugins'
.\Start-Bridge.ps1 -Python "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -VenvDirectory '.\.venv'
```

`-Python` sélectionne l’interpréteur de création de l’environnement ; adapter le chemin à l’installation Python 3.10+ x64 disponible. `-VenvDirectory` choisit l’environnement utilisé, `.venv` dans ce dossier par défaut. Les fichiers privés de session et les journaux sont par défaut dans `%LOCALAPPDATA%\CodexLocalBridges\StreamDeck\runtime`. Le token reste local et change à chaque lancement.

Le superviseur fournit `-RuntimeDirectory` avec le dossier absolu `local-installation\streamdeck` du dépôt. Ce dossier remplace les emplacements de session, journaux, verrous et sauvegardes pour ce lancement, sans modifier `LOCALAPPDATA`. Utiliser `startup\Arreter-tout.cmd` pour cette session, ou fournir le même `-RuntimeDirectory` à `Stop-Bridge.ps1`. Le lecteur média doit également recevoir `--session` avec le fichier `api-session.json` de ce dossier.

## Canvas SignalRGB complet

La version 0.2 crée le contrôleur `streamdeck-background-canvas-v2`. Son rectangle se place à l'origine du Canvas, avec une échelle de 1. Sa taille 321×201 comprend une marge technique ; l'image capturée couvre 320×200 puis est adaptée au Stream Deck 480×272. Elle conserve des détails différents à l'intérieur d'une même touche. Le mode Forced reste une couleur uniforme.

Le réglage **Background FPS** vaut 20 par défaut et accepte 1–30. Le plafond du pont est 30, afin de pouvoir modifier ce réglage sans relancer le pont. Une cadence demandée n'est pas une cadence optique garantie.

Le contrôleur expérimental `streamdeck-background-loopback` est exclu par la nouvelle version. Si SignalRGB garde l'ancien service en mémoire après remplacement du fichier, un redémarrage normal de SignalRGB peut être nécessaire pour annoncer la nouvelle identité. Le journal d'initialisation indique l'identité et la valeur FPS réellement utilisées. Ne pas modifier le registre pour forcer la migration.

## Image, GIF ou vidéo

FFmpeg doit être dans PATH. Sur la machine testée, il est déjà fourni par ImageMagick. Dans un terminal ouvert dans ce dossier :

```powershell
.\.venv\Scripts\python.exe play_background.py 'C:\chemin\animation.gif' --seconds 30 --fps 10 --loop --session "$env:LOCALAPPDATA\CodexLocalBridges\StreamDeck\runtime\api-session.json"
```

Le média HTTP a temporairement priorité sur les couleurs UDP de SignalRGB. À la fin de la lecture, SignalRGB reprend s’il envoie toujours son canvas. Les API et leurs formats sont décrits dans `API-NOTES.md`.

Les lanceurs, le moteur natif, la lecture GIF et la conservation des icônes ont été vérifiés, y compris sur une page sans fond statique. L'utilisateur a ensuite confirmé la version 0.2 : « Oui, dégradés et fluidité corrects ». La cadence mesurée est de 17 notifications acquittées/s pour une cible de 20, avec du détail spatial dans les quinze touches et sans erreur. Les compteurs sont logiciels ; aucun fonctionnement après une mise à jour de Stream Deck n'est revendiqué.
