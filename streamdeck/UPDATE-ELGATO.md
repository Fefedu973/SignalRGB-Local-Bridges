# Après une mise à jour Elgato

Le pont actuel est lié à **Stream Deck 7.5.1.22901, Windows x64, MK.2 à quinze touches**. Il ne découvre pas automatiquement les nouvelles adresses du compositeur.

## Pour l’utilisateur

1. Avant la mise à jour, arrêter le superviseur avec `startup/Arreter-tout.cmd` et suspendre son démarrage automatique. Pour un pont indépendant lancé avec les paramètres par défaut, utiliser `bridge/Arreter-StreamDeck.cmd`. Pour un runtime personnalisé, passer le même chemin absolu `-RuntimeDirectory` à `bridge/Stop-Bridge.ps1`. Attendre la confirmation d’arrêt. Le fichier `background-api.jsonl` du runtime doit montrer le déchargement (`script-unloaded`), le détachement (`detached`) et la fin (`api-finished`) : le superviseur utilise `local-installation/streamdeck` à la racine du dépôt, le lanceur indépendant utilise AppData par défaut.
2. Mettre Stream Deck à jour normalement. Ses actions et profils restent gérés par Elgato.
3. Attendre une version du pont validée pour cette nouvelle build avant de réactiver son démarrage automatique. Une build inconnue donne `Unsupported build: <fichier>` dans `launcher-stderr.log`, avant tout attachement. La nouvelle version de Stream Deck peut être utilisée normalement sans le fond animé du pont.

Ne pas supprimer les contrôles ni remplacer uniquement les empreintes pour forcer le démarrage. Une simple égalité du numéro commercial de version ne suffit pas.

## Contrôles actuels

`bridge/background_api.py` vérifie les SHA256 exacts des trois fichiers dans `C:\Program Files\Elgato\StreamDeck`, puis le chemin de l’exécutable du PID ciblé :

| Fichier | SHA256 accepté |
| --- | --- |
| StreamDeck.exe | `9B2E3D0069052F18F372B9C9AEA46E925CB463ACBA443A1075E68EC5648F769D` |
| Qt6Gui.dll | `8FCEEE959A670372AAA5763287C2EF7924CD9ECDBE2C29CF4B6C12A63079C503` |
| Qt6Core.dll | `FAE4778A42E93ADC82B831C879C886A05147E9CC26760808D21116BE5547259B` |

Le script `bridge/background-core.js` contrôle encore l’architecture, la taille d’image de l’exécutable, le chemin chargé, les prologues utilisés, les vtables, les dimensions et formats QImage et la géométrie 5×3/72×72. Un verrou par PID et la vérification des ports évitent les sessions concurrentes ordinaires.

## Portage par le mainteneur

Relever les nouvelles empreintes et analyser les nouvelles fonctions avant toute instrumentation. Revalider dans `background-core.js` les points de composition/notification, copies de vecteur Qt, métadonnées, vtables, offsets de structures, exports Qt et conventions d’appel. Les contrôles de taille, de durée de vie et de géométrie doivent rester actifs.

Après adaptation, mettre à jour `HASHES` dans `background_api.py`, les fixtures et les versions documentées. Exécuter les tests hors matériel du README, puis un essai matériel borné avec une seule session : quinze touches, icônes et actions conservées, pages avec et sans fond statique, entrée image/Canvas, expiration du bail, restauration, déchargement et détachement propres. Les acquittements seuls ne remplacent pas l’observation visuelle.

Régénérer les manifestes/archives après validation. Les clients SignalRGB, média et les lanceurs peuvent rester inchangés si leurs contrats n’ont pas changé. Le pont ne nécessite pas de recompilation C++ : les adaptations portent sur le script Frida et les contrôles Python, mais elles nécessitent une nouvelle validation native.

En cas d’erreur native ou de fermeture inattendue d’Elgato, la restauration visuelle immédiate n’est pas garantie. Ne pas enchaîner des attachements concurrents ni tuer un observateur encore en cours de nettoyage. Vérifier les journaux et rétablir proprement Stream Deck avant de poursuivre.
