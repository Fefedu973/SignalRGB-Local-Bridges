# Stream Deck : fond animé depuis SignalRGB

Ce pont transmet une image complète du Canvas SignalRGB derrière les quinze touches d’un **Stream Deck MK.2**, en conservant les actions, icônes et textes gérés par Elgato. Il utilise une instrumentation locale en mémoire, pas une API publique Elgato de streaming de fond.

Version actuellement acceptée : **Stream Deck 7.5.1.22901, Windows x64**, matériel `0FD9:0080`. Les empreintes de `StreamDeck.exe`, `Qt6Gui.dll` et `Qt6Core.dll` doivent correspondre exactement. Une autre version est refusée avant l’attachement. Lire [UPDATE-ELGATO.md](UPDATE-ELGATO.md) avant une mise à jour.

## Utilisation

Stream Deck doit être ouvert. Garder désactivé l’ancien plugin SignalRGB qui écrit directement les images USB des touches.

1. Lancer [bridge/Demarrer-StreamDeck.cmd](bridge/Demarrer-StreamDeck.cmd). Le premier lancement crée un environnement Python local et installe les dépendances épinglées. Le client SignalRGB de la session est préparé automatiquement.
2. Terminer avec [bridge/Arreter-StreamDeck.cmd](bridge/Arreter-StreamDeck.cmd). Le pont demande le retour au fond normal, décharge les hooks puis se détache. Ne pas tuer Python de force.

Les lanceurs de ce dossier n’enregistrent pas de tâche Windows. Le démarrage automatique, lorsqu’il est activé, est géré par le superviseur du dépôt parent ; consulter son README. Il ne doit y avoir qu’un seul pont pour le processus Stream Deck.

Pour choisir un Python système stable et un emplacement d’environnement, depuis le dossier du dépôt :

```powershell
.\streamdeck\bridge\Start-Bridge.ps1 -Python "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -VenvDirectory '.\streamdeck\bridge\.venv'
```

Cet exemple utilise une installation Python 3.13 par utilisateur ; adapter son chemin à l’interpréteur système installé. `-Python` sert à créer l’environnement s’il n’existe pas ; `-VenvDirectory` désigne celui utilisé ensuite. Python 3.10+ x64 est requis. Le chemin de plugins peut être explicité avec `-SignalRGBPluginDirectory`. Aucun chemin de cache Codex n’est nécessaire.

Les lanceurs indépendants conservent par défaut les jetons temporaires, journaux et marqueurs d’arrêt dans `%LOCALAPPDATA%\CodexLocalBridges\StreamDeck\runtime`. Le superviseur du dépôt fournit explicitement `-RuntimeDirectory` et utilise `local-installation\streamdeck` à la racine du dépôt, pour que l’état soit partagé entre une application Windows empaquetée et le démarrage de session ordinaire. Ce dossier contient aussi les verrous et sauvegardes privées. Aucun de ces fichiers ne doit être ajouté au dépôt ; `local-installation/` est ignoré par Git.

Pour une session supervisée, utiliser `startup\Arreter-tout.cmd`, ou passer le même chemin absolu `-RuntimeDirectory` à `bridge\Stop-Bridge.ps1`. Le raccourci d’arrêt indépendant vise seulement le runtime AppData par défaut. Ne pas lancer simultanément des ponts utilisant des dossiers de runtime différents.

## Documentation et limites

- [Démarrage détaillé et lecture GIF/vidéo](bridge/DEMARRAGE.md)
- [API HTTP/UDP et cycle de vie](bridge/API-NOTES.md)
- [Intégration SignalRGB](bridge/SIGNALRGB-INTEGRATION.md)
- [Capture et transport du Canvas](bridge/full-canvas-design.md)
- [Mise à jour Elgato](UPDATE-ELGATO.md)
- [Provenance et dépendances](PROVENANCE.md)

La version 0.2 capture 320×200 pixels source, transmet un JPEG 480×272 et découpe les quinze tuiles 72×72. Le détail spatial est conservé, avec compression et redimensionnement. La cible par défaut est 20 images/s, réglable de 1 à 30 ; il ne s’agit pas d’une garantie de cadence optique.

Une validation matérielle antérieure a confirmé visuellement les dégradés, la fluidité et la conservation des icônes. Le relevé [signalrgb-fullcanvas-live.json](validation/signalrgb-fullcanvas-live.json) comptait 1 383 images décodées, aucune erreur, les quinze touches et 17 acquittements/s dans sa dernière fenêtre de cinq secondes. Son délai entrée dans le moteur natif→acquittement était de 11 ms au 95e percentile, hors capture, transport, décodage et latence optique. Ces résultats concernent la version et le matériel indiqués ; ils ne valident pas une mise à jour Elgato.

## Tests sans matériel

Depuis `streamdeck/bridge`, avec les dépendances installées :

```powershell
python -B -m unittest -v test_background_api.py test_canvas_transport.py test_install_signalrgb_background.py test_media_frames.py
node test_signalrgb_background.cjs
node test_background_layout.cjs
node test_background_pacing.cjs
powershell.exe -NoProfile -File Test-RuntimeDirectory.ps1
```

Les tests Python incluent de vrais JPEG/GIF décodés hors de Stream Deck ; FFmpeg doit être disponible pour les tests média. Les tests natifs utilisent des fixtures mémoire, sans attachement. Le relevé de déplacement figure dans [validation/relocation-tests.json](validation/relocation-tests.json). Le [contrôle des runtimes partagés](validation/runtime-tests.json) couvre 35 tests Python, 27 JavaScript et 40 assertions PowerShell 5.1, sans exécuter les lanceurs. Les anciens relevés sont conservés comme preuves historiques, sans jeton ni profil utilisateur.

Le manifeste SHA256 porte sur les blobs Git publiés (et le contenu des archives Git), avant conversion éventuelle des fins de ligne par Windows lors du checkout.
