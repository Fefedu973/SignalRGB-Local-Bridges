# Démarrage automatique des ponts locaux

Ce gestionnaire lance les ponts Govee BLE, NVIDIA NVAPI et Stream Deck à l’ouverture de session Windows. Il ne dépend pas de Codex et ne nécessite pas de droits administrateur. Les applications SignalRGB et Elgato conservent leurs propres réglages de démarrage.

Le superviseur démarre Govee et NVIDIA, puis attend qu’un seul processus Elgato soit présent avant de lancer son pont. Il surveille les processus et les ports locaux, relance un pont terminé et attend sa disparition complète avant toute nouvelle tentative. Un port déjà occupé, notamment par un ancien pont du dossier `outputs`, empêche un doublon. Un processus encore vivant mais bloqué n’est jamais tué automatiquement.

## Préparation

Les dossiers doivent rester à leurs emplacements définitifs :

```text
Projects/
  SignalRGB-Local-Bridges/
    startup/
    nvidia/
    streamdeck/bridge/          # contient son .venv
    local-installation/        # prive, ignore par Git
  signalrgb-govee-direct-connect/ble-companion/
```

Python x64 doit être installé durablement. Le pont Govee et celui de Stream Deck doivent disposer de leurs environnements Python et dépendances. Le gestionnaire n’installe rien en arrière-plan : ses préconditions vérifient les fichiers nécessaires. Les lanceurs de chaque pont restent responsables de leurs propres validations.

Placer la configuration Govee privée dans `SignalRGB-Local-Bridges\local-installation\govee\config.local.json`, puis créer une fois la configuration du gestionnaire en donnant les chemins réels :

```powershell
.\Initialize-Config.ps1 -Python "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" `
  -GoveePython "CHEMIN_ABSOLU_DU_VENV_GOVEE\Scripts\python.exe"
.\Start-Supervisor.ps1 -Check
```

`-HubDirectory` (alias `-HubRoot`), `-GoveeDirectory` (alias `-GoveeRoot`) et `-SignalRGBPluginDirectory` permettent d’adapter l’installation. `-GoveeDirectory` désigne le dossier `ble-companion`, pas la racine Git. `-Force` remplace explicitement une configuration déjà créée.

La configuration du gestionnaire est `<hub>\local-installation\config.json`. Elle ne contient que des chemins. La configuration Govee et sa clé restent dans `<hub>\local-installation\govee\config.local.json`. Le dossier `local-installation` doit rester ignoré par Git ; aucun de ces fichiers privés ne doit être ajouté au dépôt. `config.example.json` est un modèle public sans secret.

Les états de fonctionnement utilisent aussi des chemins explicites partagés : `local-installation\startup`, `local-installation\nvidia` et `local-installation\streamdeck`. Cela évite la virtualisation AppData des applications MSIX : un fichier écrit depuis Codex dans son AppData peut être invisible à une tâche Windows extérieure à Codex. Aucune variable système, notamment `LOCALAPPDATA`, n’est remplacée. Les paramètres `-RuntimeDirectory` des lanceurs NVIDIA et Stream Deck désignent les mêmes dossiers pour le démarrage et l’arrêt.

## Utilisation

- `Installer-demarrage.cmd` enregistre le lancement à l’ouverture de session. Il ne lance aucun pont immédiatement.
- `Demarrer-tout.cmd` lance le superviseur caché pour la session actuelle. Un verrou par utilisateur empêche deux superviseurs simultanés.
- `Arreter-tout.cmd` demande l’arrêt du superviseur puis le nettoyage de chaque pont. Il ne ferme ni SignalRGB ni Elgato et laisse le démarrage automatique installé.
- `Desactiver-demarrage.cmd` retire le démarrage automatique et demande l’arrêt propre. `Disable-Autostart.ps1 -KeepRunning` retire seulement l’automatisme.

Le gestionnaire utilise la tâche planifiée **SignalRGB Local Bridges**, à l’ouverture de session de l’utilisateur courant, avec privilèges limités et session interactive. Si Windows refuse sa création, il utilise uniquement l’entrée utilisateur `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\SignalRGBLocalBridges`. Aucun mot de passe, service système ni contournement de privilèges n’est utilisé.

Le repli Run appelle `wscript.exe` et un petit fichier privé `<hub>\local-installation\startup\logon.vbs`. Celui-ci lance PowerShell sans fenêtre ; les longs chemins du dépôt et de la configuration restent dans ce fichier. L’installeur vérifie que l’entrée Run ne dépasse pas 260 caractères et refuse le repli si Windows Script Host est absent ou désactivé. La désactivation supprime aussi ce lanceur privé. `Install-Autostart.ps1 -Check` affiche la longueur prévue sans rien enregistrer.

Les tentatives après échec sont espacées de 5, 15 puis 60 secondes, ensuite de 5 minutes. Un fonctionnement observé pendant une minute réinitialise ce compteur. Les fenêtres de surveillance peuvent ajouter jusqu’à 10 secondes. Les applications doivent rester exécutées par le même utilisateur et avec des privilèges compatibles ; le gestionnaire n’élève pas Elgato.

La tâche Windows ne relance pas elle-même le superviseur après son arrêt : cela évite qu’une reprise déjà programmée annule un arrêt manuel. Les reprises des ponts sont gérées par le superviseur. Si ce dernier rencontre une erreur fatale, son journal l’indique et `Demarrer-tout.cmd` permet de le relancer.

## Redémarrages et mises à jour Elgato

Un redémarrage de SignalRGB ne coupe pas les ponts. Si Elgato se ferme, son pont se détache ; lorsque l’application revient, le superviseur attend la fin du précédent pont puis en lance un nouveau.

Avant chaque nouvel attachement, les empreintes SHA-256 de `StreamDeck.exe`, `Qt6Gui.dll` et `Qt6Core.dll` doivent correspondre à l’allowlist du pont. Une version différente est refusée sans attachement et sans boucle de relancement. Les changements des fichiers Elgato ou du script du pont déclenchent une nouvelle vérification.

Après une mise à jour Elgato non encore prise en charge, le fond animé reste donc indisponible ; les boutons et fonctions normales d’Elgato restent utilisables. Il faut adapter et tester le pont pour cette version. **Remplacer seulement les empreintes n’est pas une mise à jour sûre** : les points d’accroche et structures doivent être revalidés. Govee et NVIDIA continuent indépendamment.

## Diagnostic et validation

Les journaux, l’état du superviseur et les sorties des lanceurs sont dans `<hub>\local-installation\startup`. Le journal principal est `supervisor.jsonl`, avec une rotation à 2 Mio. `bootstrap.log` recueille aussi les erreurs précédant l’initialisation du superviseur, comme une configuration introuvable. `unsupported-elgato` signifie un binaire inconnu ou un chemin de processus différent ; `waiting-process` signifie qu’un processus ou son lanceur existe encore et interdit un chevauchement. La présence d’un port constitue un contrôle de disponibilité, pas une nouvelle validation des couleurs sur le matériel.

`Test-Startup.ps1` vérifie hors matériel la syntaxe, les chemins, les décisions empêchant les doublons, le délai des reprises, les refus de versions Elgato et le verrou entre deux processus. Il ne modifie ni tâches planifiées ni registre et ne lance aucun pont.

`Test-LauncherExit.ps1` vérifie les codes de sortie 0 et 3 avec de petits lanceurs inoffensifs, ainsi que leur sortie redirigée. `Test-Sha256.ps1` vérifie les empreintes sans dépendre de la commande PowerShell `Get-FileHash`.

`Install-Autostart.ps1 -Check` valide l’installation sans l’enregistrer. `Start-Supervisor.ps1 -Check` vérifie également les empreintes locales, sans attachement ni commande matérielle.

L’arrêt utilise uniquement les marqueurs et lanceurs de nettoyage existants. Aucun processus Frida ou pont n’est tué de force. Si un lanceur reste bloqué ou un nettoyage ne se confirme pas, consulter les journaux avant de relancer. Lors d’un arrêt Windows, le système peut interrompre les processus avant qu’une restauration complète se termine ; utiliser l’arrêt explicite lorsque cette restauration doit être vérifiée.
