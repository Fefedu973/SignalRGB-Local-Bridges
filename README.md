# SignalRGB Local Bridges

Ponts Windows pour piloter le fond du Stream Deck et l'éclairage d'une RTX 3080 Ti Founders Edition depuis SignalRGB. Ce dépôt contient aussi le démarrage automatique commun avec le compagnon Bluetooth Govee, maintenu dans son propre dépôt.

## Projets du 19 septembre 2026

| Projet | Livrable et portée vérifiée |
| --- | --- |
| [Stream Deck](streamdeck/README.md) | Canvas complet derrière les quinze touches du MK.2, actions/icônes/textes conservés ; Elgato **7.5.1.22901 x64** uniquement. |
| [NVIDIA](nvidia/README.md) | RTX 3080 Ti FE, une zone RGBW et une zone blanche à intensité réglable ; NVAPI sans OpenRGB ni service administrateur. |
| [Govee Direct Connect](https://github.com/Fefedu973/signalrgb-govee-direct-connect) | Récupération des IP LAN, transport Bluetooth temps réel H6008, profils Bluetooth extensibles et H6159 classique avec extinction réelle au noir. |
| [Alienware Monitor RGB](https://github.com/Fefedu973/AW3423DWF-SignalRGB-Plugin) | Plugin SignalRGB, portage source OpenRGB, matrice des modèles, protocoles, historique et outils. Consulter les limites de validation de chaque modèle. |

Les protocoles et comportements ont été vérifiés sur le matériel disponible ; cette publication ne revendique pas la compatibilité avec toute une gamme à partir du seul nom commercial. Le correctif ASUS jaune a été résolu par l'utilisateur dans sa configuration et ne fait pas l'objet d'un patch générique.

## Installation durable

Placer ce dépôt et `signalrgb-govee-direct-connect` côte à côte dans un dossier de projets permanent. Installer Python **3.13 x64** ; les dépendances testées sont dans les fichiers de chaque projet. Les environnements `.venv` sont locaux et ne se déplacent pas : les recréer si le chemin des projets ou de Python change.

Pour Govee, créer `.venv` à la racine de son dépôt et installer `ble-companion/requirements-windows-py313.lock.txt`. Conserver sa configuration personnelle dans `local-installation/govee/config.local.json` de ce dépôt, ignoré par Git. Voir le README du compagnon pour le schéma ; aucune clé personnelle n'est fournie.

Pour Stream Deck, le lanceur peut créer `streamdeck/bridge/.venv` et installer `streamdeck/bridge/requirements.txt`. NVIDIA utilise uniquement la bibliothèque standard Python et le pilote installé.

Le [guide de démarrage Windows](startup/README.md) détaille la configuration privée et l'installation du superviseur. Il démarre à **l'ouverture de session de l'utilisateur**, sans élévation. Une session Windows et le Bluetooth doivent donc être disponibles ; ce n'est pas un service avant connexion. Il attend l'application Elgato pour son pont. SignalRGB et Elgato conservent leurs propres réglages de lancement Windows.

Les raccourcis utiles sont dans `startup/` :

- `Demarrer-tout.cmd` : démarrer le superviseur et les ponts configurés.
- `Arreter-tout.cmd` : suspendre le superviseur et arrêter proprement les ponts.
- `Installer-demarrage.cmd` : enregistrer le démarrage à l'ouverture de session.
- `Desactiver-demarrage.cmd` : désactiver ce démarrage et arrêter proprement.

Le superviseur évite les doublons, journalise les erreurs et espace les tentatives de reprise. Les journaux, paramètres et jetons restent dans `local-installation/`, explicitement ignoré par Git et absent des archives publiques. Ce chemin partagé évite la virtualisation AppData des applications MSIX : les processus lancés par Windows voient les mêmes fichiers que ceux lancés manuellement. Ne pas lancer une deuxième copie des anciens ponts depuis un dossier de recherche.

## Après une mise à jour Elgato

Lire [la procédure complète](streamdeck/UPDATE-ELGATO.md). Arrêter proprement le superviseur avant la mise à jour. Le pont vérifie les empreintes de trois binaires Elgato avant tout attachement : une build inconnue reste inutilisée jusqu'à adaptation et validation du hook. Elgato reste utilisable normalement. Changer seulement les empreintes n'est pas un portage.

Le pont intervient en mémoire ; il ne modifie pas les binaires Elgato sur disque. Les profils Stream Deck restent gérés par Elgato.

## Sources, archives et licence

Les sources, tests, instructions et relevés expurgés sont publiés. Les environnements Python, captures brutes, messages privés, configurations personnelles, jetons de session et binaires propriétaires sont exclus. Les éventuelles archives locales `private-archives/` sont volontairement ignorées par Git et les paquets publics.

Licence **GPL-2.0-or-later**, voir [LICENSE](LICENSE), [provenance Stream Deck](streamdeck/PROVENANCE.md) et [attributions NVIDIA](nvidia/THIRD_PARTY_NOTICES.md). Les logiciels et bibliothèques tiers gardent leurs licences ; leurs binaires ne sont pas redistribués ici.
