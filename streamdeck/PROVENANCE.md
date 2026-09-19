# Provenance et dépendances

Le pont Python, le moteur Frida, le client SignalRGB, les lanceurs et leurs tests ont été développés pour cette intégration. Les anciennes captures USB, profils Elgato, ressources d’actions utilisateur, données de compte, jetons, sauvegardes et environnements Python ne sont pas distribués ici. Aucun exécutable ni bibliothèque Elgato/Qt n’est copié dans ce dossier.

L’implémentation utilise les exports Qt présents dans l’application et des points internes du compositeur identifiés sur Stream Deck 7.5.1.22901. C’est une intégration indépendante, sans affiliation ni approbation Elgato ou SignalRGB. Les marques restent celles de leurs propriétaires. La [recherche des API publiques](research-official.md) et les [notes du Canvas](bridge/full-canvas-design.md) identifient les sources techniques ; les numéros de version y décrivent la date de l’investigation.

Les dépendances sont installées séparément, elles ne sont pas vendoriées :

| Dépendance | Version prévue | Provenance/licence déclarée |
| --- | --- | --- |
| Frida Python | 17.18.0 | Métadonnées de distribution : wxWindows Library Licence, Version 3.1 ; projet https://frida.re |
| Pillow | 12.3.0 | Métadonnées de distribution : `MIT-CMU` ; projet https://python-pillow.org |
| FFmpeg | Exécutable disponible dans PATH | Utilisé uniquement pour les médias et leurs tests ; sa licence dépend de la build installée. Aucun binaire fourni. |
| Python / Node.js | Python 3.10+ x64 ; Node pour les tests JS | Outils externes, non distribués dans ce dossier. |

Le code original de ce dossier est distribué sous **GPL-2.0-or-later**, conformément à la [licence du dépôt parent](../LICENSE). Ce fichier ne remplace pas les licences des dépendances et n’accorde aucun droit sur les binaires Elgato. Les empreintes et courts prologues servent uniquement à vérifier la build compatible.

Les jetons présents dans les tests sont des chaînes synthétiques explicitement nommées. Le seul jeton du modèle SignalRGB distribué est `__LOCAL_SESSION_TOKEN__`; une valeur réelle est générée et installée localement pour chaque session.
