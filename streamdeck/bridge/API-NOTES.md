# Fond animé natif Stream Deck — prototype local

Le pont change le fond temporaire avant que Stream Deck dessine les icônes et les textes. Il conserve les actions, leurs paramètres et les profils. **L’utilisateur a confirmé que les quinze touches suivent l’animation avec leurs icônes préservées.**

La version 0.2 ajoute le Canvas SignalRGB complet : capture native 320×200, JPEG 480×272 puis découpage de quinze tuiles de 72×72. L'utilisateur a également confirmé cette version : « Oui, dégradés et fluidité corrects ». Le relevé final compte 1 383 images décodées, aucune erreur ou rejet, quinze touches et 17 acquittements/s sur cinq secondes pour une cible de 20. Chaque touche présente 17–20 couleurs distinctes parmi vingt échantillons. Le délai entrée dans le moteur natif→acquittement vaut 11 ms au 95e percentile, sans inclure extraction, transport ou décodage ; aucune latence optique n'est mesurée.

Le prototype est limité à Stream Deck **7.5.1.22901**, Windows x64, et au **MK.2 à quinze touches**. Les hash de StreamDeck.exe et de ses bibliothèques Qt sont vérifiés avant l’attachement, puis les chemins et prologues sont contrôlés en mémoire. Une version incompatible est refusée.

## Exécution

Stream Deck doit être déjà ouvert. Fermer proprement un ancien observateur avant tout nouvel attachement. Le verrou par PID protège les scripts de ce dossier. Un autre plugin qui écrit directement les images USB du Stream Deck doit être désactivé.

```powershell
python background_api.py --pid <PID-StreamDeck> --seconds 600 --output background-api.jsonl
```

La durée par défaut est de dix minutes. `--seconds 0` active explicitement une session sans échéance, jusqu’à l’arrêt propre, à la fermeture de Stream Deck ou à une erreur native. Le lanceur direct n’enregistre pas de tâche Windows ; le superviseur du dépôt parent peut gérer le démarrage automatique. Les dépendances épinglées sont `frida==17.18.0` et `Pillow==12.3.0` ; Pillow décode les JPEG hors du processus Stream Deck. Les deux fichiers `Demarrer-StreamDeck.cmd` et `Arreter-StreamDeck.cmd` gèrent ce mode quotidien. Le premier crée un environnement `.venv` et installe les dépendances.

Le lanceur quotidien conserve par défaut le token et les journaux dans `%LOCALAPPDATA%\CodexLocalBridges\StreamDeck\runtime`, en dehors du livrable. Le superviseur utilise explicitement `-RuntimeDirectory` / `--runtime-directory` pour les placer dans `local-installation/streamdeck` du dépôt, avec les verrous et sauvegardes du client ; ce dossier privé est ignoré par Git. `LOCALAPPDATA` n'est pas redéfini. Il faut fournir le même runtime au lanceur d'arrêt. Le pont installe le client SignalRGB avec le token courant puis le rend inerte lors de l’arrêt propre. L’option `--signalrgb-plugin-dir` permet de préciser le dossier des plugins.

Le premier rendu naturel d’une touche identifie le compositeur. `/health` peut rester `ready:false` jusqu’au prochain rafraîchissement d’une horloge. Aucun pointeur d’une ancienne session n’est repris. Un candidat incompatible est ignoré avant de retenir son pointeur. Quand la page n’a aucun fond statique, le vecteur natif de positions est vide : le pont accepte ce seul cas après vérification des vtables, de la grille 5×3, des tuiles 72×72 et de l’image temporaire (format et stride). Il emploie alors les coordonnées MK.2 mesurées lors de la capture réussie, avec `source: "verified-mk2-fallback"` dans `/layout`. Un vecteur non vide de taille différente reste refusé.

`api-session.json` contient le token temporaire et les ports locaux. Ne pas publier ce fichier. Il est supprimé à l’arrêt normal. Pour arrêter le pont, créer le fichier `<output>.stop`, puis laisser le script restaurer le fond, décharger les hooks et se détacher. Ne pas tuer Python pour arrêter Frida.

## Contrat HTTP

Adresse : `http://127.0.0.1:47686`. Chaque requête porte `Authorization: Bearer <token>`. Les requêtes provenant d’une page web avec un en-tête `Origin` sont refusées. Le client local n’utilise pas de proxy.

| Endpoint | Contenu ou résultat |
|---|---|
| `GET /health` | État `ready`, compteurs, erreurs et notification en attente |
| `GET /layout` | `width`, `height`, `tileWidth`, `tileHeight`, quinze `positions` natives, colonnes et lignes |
| `POST /colors` | JSON `{"colors":[[R,G,B],…15],"lease_ms":2000}` |
| `POST /frame` | `application/octet-stream` : quinze tuiles 72×72 BGRA concaténées, exactement 311040 octets, alpha 255 |
| `POST /stop` | Désarme le remplacement et demande un rendu normal |

Pour `/frame`, `X-Lease-Ms` est facultatif et vaut 2000 par défaut. Les baux sont limités à 500–10000 ms. Sans nouvelle donnée avant expiration, le moteur restaure le fond normal. Le pont garde la trame la plus récente et une seule notification Qt identifiée en attente. `--max-fps` règle le plafond natif de 1 à 30, avec 30 par défaut dans l'API. Le client SignalRGB demande 20 par défaut et permet 1–30. Les données de `status.pacing` permettent de comparer les cadences demandées, émises et acquittées ; elles ne mesurent pas les pixels physiquement affichés.

## Contrat UDP

Adresse : `127.0.0.1:47685`. Le mode couleur uniforme conserve les champs de `/colors`, plus `"token":"…"`. Le mode Canvas utilise :

```javascript
{token, kind:"canvas-jpeg", frame, part, total, data:[/* octets */], lease_ms:2000}
```

Chaque fragment transporte au plus 1 024 octets JPEG. Une image est limitée à 256 KiB et 256 fragments ; `frame` est un entier croissant dans la plage sûre JavaScript, `part` commence à zéro. L'assemblage garde uniquement la trame la plus récente et expire après 250 ms. Le JPEG doit décoder exactement en 480×272 avant découpage selon `/layout`. Le client passe une chaîne `JSON.stringify(...)` à `socket.write` : cette surcharge produit du JSON compact brut, contrairement à la surcharge objet qui ajoute une indentation. Les datagrammes du client restent sous 5 KiB ; le serveur dispose d'un tampon de réception complet et traite Windows10040 comme un rejet non fatal.

Les datagrammes invalides sont ignorés. Un lot borné conserve la dernière image complète. Aucun paquet n'est envoyé sur le réseau local. `/health.canvas` expose les images décodées, rejets, assemblages abandonnés, durée du dernier décodage et nombre de couleurs distinctes échantillonnées dans chaque touche.

Les frames et couleurs HTTP ont priorité pendant leur bail, afin que le Canvas SignalRGB ne remplace pas un GIF en cours. Les images ou couleurs UDP reprennent après `/stop` ou l’expiration du bail HTTP.

## Images, GIF et vidéos

`play_background.py` utilise FFmpeg hors du processus Stream Deck. Il ajuste le média au canvas natif, le découpe selon `/layout`, envoie les tuiles et appelle `/stop` à la fin.

```powershell
python play_background.py animation.gif --seconds 30 --fps 10 --loop
```

Le MK.2 observé a un canvas 480×272 et des tuiles 72×72 aux positions X 11/108/205/302/399 et Y 5/102/199. Le client lit ces valeurs à chaque session.

## Validation et mécanisme

- Le remplissage sur composition naturelle a modifié puis restauré deux touches, sans erreur.
- Le signal Qt natif est reçu sur son thread habituel via une connexion queued existante. Son vecteur copié est identifié précisément, ce qui distingue nos acquittements des animations propres à l’application.
- Un premier essai RGB de vingt secondes a produit 163 mises à jour et une restauration, sans erreur. Il ne composait toutefois que neuf touches : le cache de rendu différé évitait le recalcul des images fixes.
- Le correctif conserve les flags de rendu et ajoute le bit de composition immédiate uniquement pendant nos notifications, restauration comprise. Son essai a composé et restauré les quinze touches : 50 notifications, 736 remplissages, zéro erreur. Détachement normal à 16:45:36 UTC. L’utilisateur a confirmé le résultat visuel.
- Les images des touches de la croix sont transparentes. Le problème ne provenait pas d’icônes opaques.
- Le nouvel essai API avec le correctif des quinze touches a accepté 96 frames GIF : 83 notifications acquittées sur 83, 1230 peintures, les quinze indices de touches présents, une restauration et zéro erreur. Cette validation a été effectuée par le lanceur de test coordonné avec l’utilisateur.
- Le prototype du lanceur quotidien a ensuite démarré sans fond statique de page : sélection au premier rendu naturel à 17:10:00 UTC, `source: "verified-mk2-fallback"`. L'utilisateur a confirmé l'animation visible, puis demandé le détail complet du Canvas. Les mesures du prototype à quinze couleurs restent historiques ; le résultat 0.2 est décrit en tête de ce document.
- Dix tests API hors matériel couvrent authentification, origine web, tailles, alpha, couleurs, priorité HTTP, expiration, parsing de la durée et arrêt du mode illimité par fichier, détachement ou faute. Cinq tests supplémentaires exercent la sélection native et le cas sans fond statique avec des fixtures mémoire. Les composants média et SignalRGB ont leurs tests séparés.

Les images utilisent l’export public `QImage::bits()`, qui détache l’image temporaire avant l’écriture. Les formats, dimensions et stride sont contrôlés ; le fond stocké dans le profil n’est pas modifié. Aucune fonction interne de rendu n’est appelée directement et aucun paquet USB n’est construit par ce pont.

En cas d’exception native ou d’absence d’acquittement pendant trois secondes, le pont cesse les envois. Après une telle erreur, un retour immédiat au fond normal n’est pas garanti : un rendu naturel ou une relance propre peut être nécessaire. Le support d’autres versions ou modèles n’est pas revendiqué.
