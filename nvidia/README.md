# RTX 3080 Ti Founders Edition — SignalRGB sans OpenRGB

Ce pont Windows pilote directement l’éclairage par la DLL NVAPI déjà installée avec le pilote NVIDIA. OpenRGB, un pilote supplémentaire et des droits administrateur ne sont pas nécessaires. SignalRGB fournit les deux couleurs du Canvas au petit processus Python local.

## Utilisation

1. Le client `NVIDIA_RTX3080Ti_FE_Bridge.js` est installé dans le dossier Plugins SignalRGB de OneDrive. `Installer-client.cmd` permet de le réinstaller. Un redémarrage de SignalRGB peut être nécessaire pour découvrir un nouveau fichier.
2. Double-cliquer `Lancer-pont.cmd`. Le lancement reste discret et évite les instances en double.
3. Dans SignalRGB, placer **RTX 3080 Ti FE — RGBW + monochrome** sur le Canvas. Les paramètres permettent aussi une couleur fixe et une luminosité globale.
4. `Arreter-pont.cmd` arrête proprement le pont et restaure l’état présent avant sa première écriture. Fermer le rendu SignalRGB libère également le GPU après deux secondes sans échantillon.

Le lanceur peut être utilisé seul ou par le [gestionnaire de démarrage Windows](../startup/README.md) du dépôt. Python 3 utilise uniquement sa bibliothèque standard ; le lanceur accepte `-Python`, puis cherche un environnement local ou une installation Python via `py.exe`. Il ne dépend pas du cache Codex. Les journaux et le marqueur d’arrêt sont par défaut dans `%LOCALAPPDATA%\NvidiaFeBridge`. Le superviseur fournit `-RuntimeDirectory` avec le chemin absolu `local-installation\nvidia` du dépôt pour partager l’état entre contextes Windows empaqueté et ordinaire. Ce dossier privé est ignoré par Git. Utiliser `startup\Arreter-tout.cmd`, ou passer le même `-RuntimeDirectory` à `Stop-Bridge.ps1` ; le raccourci indépendant vise seulement le runtime AppData par défaut.

## Les deux zones réelles

| Point Canvas | Capacité NVAPI | Traitement |
|---|---|---|
| Front RGBW | Type 3 RGBW, emplacement 8 | Couleur RGB ; les gris presque neutres utilisent le canal blanc |
| Top / logo | Type 4 SINGLE_COLOR, emplacement 0 | Intensité monochrome, de 0 à 100 %, calculée avec le canal RGB le plus fort |

La deuxième zone n’est pas RGB d’après le pilote de cette carte. Sa couleur physique ne peut donc pas être changée par ce pont. Les positions et noms proviennent du pilote/OpenRGB et peuvent être ajustés sur le Canvas.

Seul le périphérique PCI **10DE:2208, sous-système 10DE:1535** est accepté. Le modèle présent est une RTX 3080 Ti FE avec pilote 616.92. Il faut exactement deux zones avec les types 3 et 4 attendus.

## Validation du 19 septembre 2026

- Lecture des capacités et du contrôle NVAPI réussie sans écriture.
- Test matériel de six secondes : RGBW rouge, vert, bleu, et intensité monochrome 25 %, 63 %, 0 %. Les trois relectures correspondent exactement aux consignes.
- Restauration du bloc original entier de 6 476 octets, comparaison binaire exacte réussie. Voir `validation/gpu-test.json`.
- Dix tests Python sans GPU : structure binaire, préservation des réservés, conversion, validation stricte, coalescence, bail, restauration et récupération après écriture partielle simulée. Le test réseau utilise de vrais sockets UDP loopback et ferme le client avant la réponse, puis vérifie que le serveur accepte encore un autre client (erreurs Windows 10054/10052).
- Le module ES réel du client est lié et exécuté en VM avec UDP simulé : Canvas, couleur fixe, JSON, 100 ms, rafraîchissement 500 ms, découverte et arrêt passent.
- Revue croisée indépendante de l’ABI et des flags effectuée.
- Après redémarrage de SignalRGB à 19:50, le moteur du plugin est actif : 369 écritures GPU confirmées par le pont, deux couleurs de Canvas distinctes, bail vivant et aucune erreur NVAPI. Voir `validation/signal-runtime-status.json`. Après mise à jour du client 0.1.1, le pont reste en streaming avec 925 écritures et aucune erreur (`validation/signal-runtime-0.1.1.json`). La version 0.1.1 conserve la catégorie réseau par défaut pour éviter une déclaration de bus PCI non applicable au pont.

Validation visuelle confirmée par l’utilisateur le 19 septembre 2026 : « Oui, la carte suit SignalRGB ». Le fonctionnement physique complète les relectures NVAPI et la preuve du flux Canvas.

## Fonctionnement et API locale

UDP **127.0.0.1:47687**, jamais une interface réseau externe. Le serveur accepte au plus 4 096 octets par message, deux triplets d’octets et une luminosité entière de 0 à 100. Aucun compte ni secret n’est requis.

```json
{"id":1,"op":"colors","colors":[[255,0,0],[128,128,128]],"brightness":100}
```

Les opérations `status`, `heartbeat` et `release` renvoient un état JSON avec l’identifiant reçu, `ok`, `state`, `writes`, `last_colors`, `restored_exact`, `error` et `lease_ms`. Le dernier échantillon remplace les précédents ; les écritures sont espacées d’au moins 100 ms et les couleurs identiques ne déclenchent aucune nouvelle écriture GPU. Le client renvoie les couleurs toutes les 500 ms pour renouveler le bail et permettre un redémarrage du serveur.

Le premier échantillon sauvegarde l’état courant complet. Les appels SetControl utilisent toujours **flags 0 / bDefault 0**, donc l’état volatil. Le code ne touche ni firmware, ni réglage par défaut, ni NVRAM. Un arrêt normal, un bail expiré ou une erreur déclenche la restauration ; une erreur de restauration reste explicitement signalée et conserve le snapshot en mémoire pour une nouvelle tentative. Une terminaison forcée du processus ou une coupure électrique ne peut pas garantir l’exécution du bloc de restauration.

```powershell
python -B gpu_bridge.py                              # lecture seule
python -B -m unittest -q                            # tests sans matériel
node --experimental-vm-modules test_client.cjs       # client réel avec UDP simulé
python -B gpu_bridge.py --serve --allow-write         # mode serveur explicite
```

Ne pas lancer simultanément un autre logiciel qui écrit les mêmes zones GPU. L’extension Command Palette `OpenRgbController` présente sur ce PC est un client OpenRGB ponctuel ; elle était inactive, sans connexion TCP, lors de la validation. Aucun arrêt ni modification de cette extension n’a été nécessaire.

## Sources et licence

Le code de ce dossier est distribué sous **GPL-2.0-or-later**, voir `LICENSE` et `THIRD_PARTY_NOTICES.md`. La DLL NVIDIA est chargée depuis Windows et n’est pas redistribuée.

- [Documentation NVIDIA NVAPI](https://docs.nvidia.com/nvapi/nvapi_8h.html) : interfaces d’éclairage GPU.
- [Structure officielle de contrôle d’une zone](https://docs.nvidia.com/nvapi/struct__NV__GPU__CLIENT__ILLUM__ZONE__CONTROL__V1.html) : type, mode, union et champs réservés.
- [OpenRGB, révision exacte étudiée](https://github.com/CalcProgrammer1/OpenRGB/tree/cd44e41d462629410a806119694a773e88449ce1/Controllers/NVIDIAIlluminationController) : correspondance FE, formats et conversion RGBW.
- [Documentation des plugins SignalRGB](https://docs.signalrgb.com/developer/plugins/plugin-exports/) : client réseau et exports du plugin. Aucune liaison NVAPI d’éclairage accessible aux plugins JS n’a été trouvée dans l’API consultée ; le processus local fournit cette liaison.
