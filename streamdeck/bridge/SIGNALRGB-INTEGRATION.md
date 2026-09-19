# SignalRGB : Canvas complet vers le fond Stream Deck

Le client version **0.2.0** extrait une image du Canvas actif en un seul appel natif `device.getImageBuffer`. Il couvre 320×200 pixels source, produit un JPEG de 480×272, puis le pont découpe les quinze tuiles 72×72. Les détails restent visibles à l'intérieur de chaque touche, sous les icônes et textes d'Elgato. Le mode Forced reste une couleur uniforme.

Ce périphérique est réseau : aucun VID/PID, aucune ouverture HID, aucun appel USB. Son unique module est `@SignalRGB/udp` et son destinataire est `127.0.0.1`. L'ancien plugin USB qui remplace les images complètes des touches doit rester désactivé.

## Résultat réel

Le 19 septembre 2026, l'utilisateur a confirmé : « Oui, dégradés et fluidité corrects ». Le relevé final compte 1 383 images Canvas décodées, zéro rejet, zéro erreur native et les quinze touches peintes. Sur la fenêtre de cinq secondes, la cadence est de **17 notifications acquittées/s** pour une cible client de 20 et un plafond serveur de 30. Le délai entrée dans le moteur natif→acquittement vaut **11 ms au 95e percentile**, sur 256 observations. Ce délai exclut l'extraction, le transport et le décodage ; il s'agit d'une mesure du logiciel hôte, pas d'une mesure optique.

Chaque touche contient 17 à 20 couleurs distinctes parmi vingt pixels échantillonnés. Une image JPEG récupérée passivement présente 386 couleurs. Ces preuves distinguent la version 0.2 du prototype à une couleur par touche. Les métriques anonymisées figurent dans `../validation/signalrgb-fullcanvas-live.json`.

## Géométrie et migration

Le contrôleur porte l'identité **`streamdeck-background-canvas-v2`**. Ses défauts sont une position `[0,0]`, une échelle `1` et une taille `[321,201]`. La marge d'un pixel respecte la borne stricte de l'API native, qui exige x+largeur < taille et y+hauteur < taille. La capture utile est `[0,0,320,200]`, redimensionnée en 480×272, sans retournement horizontal ou vertical.

Les quinze positions LED affichées dans SignalRGB suivent les centres physiques des touches, convertis en coordonnées source. Elles ne déterminent pas la résolution de l'image capturée. Une image JPEG redimensionnée conserve le détail spatial mais n'est pas une copie sans perte des pixels d'origine.

L'ancienne identité `streamdeck-background-loopback` est refusée par Validate et par Initialize. Cette nouvelle identité évite de réutiliser l'échelle 8 du prototype. Aucun réglage de registre n'est écrit directement. Si un service ancien reste chargé après modification du fichier, un redémarrage normal de SignalRGB peut être nécessaire ; le journal d'initialisation affiche l'identité et la valeur FPS effectivement reçues.

## Installation par session

L'option `--install-signalrgb` appelle l'installateur après publication de la session API. Il valide le jeton et les ports, vérifie l'API locale, prépare l'interface QML de même nom, puis installe atomiquement le JavaScript avec le jeton courant. L'appel depuis le serveur utilise un contrôle interne de santé et de session ; la commande autonome emploie un GET /health authentifié sans proxy ni redirection.

Le jeton change automatiquement à chaque lancement. Le modèle livré conserve `__LOCAL_SESSION_TOKEN__` et reste inerte sans installation. Les sauvegardes sont privées, dans `%LOCALAPPDATA%\CodexLocalBridges\StreamDeck\signalrgb-backups`. L'arrêt normal rend le client inerte uniquement si sa copie n'a pas été modifiée depuis l'installation.

L'installateur choisit l'unique dossier Plugins existant entre Documents Windows et les emplacements OneDrive déclarés. En cas d'ambiguïté, fournir le chemin explicitement. Le lanceur quotidien utilise le dossier `%USERPROFILE%\OneDrive\Documents\WhirlwindFX\Plugins` lorsqu’il existe, ou accepte `-SignalRGBPluginDirectory` pour l’emplacement réellement utilisé par SignalRGB.

## Transport et cadence

Le client demande **20 images/s par défaut**, réglables de 1 à 30. Il demande une cible moteur de 60 Hz, avec RenderFrameDelay de 10 ms, puis limite ses captures par horloge. Il ne bloque pas la boucle avec device.pause.

Le JPEG est limité à 256 KiB et divisé en au plus 256 fragments de 1 024 octets :

```javascript
{token, kind:"canvas-jpeg", frame, part, total, data:[/* octets */], lease_ms:2000}
```

Chaque message est envoyé comme chaîne JSON compacte, afin d'éviter l'indentation des tableaux par la surcharge objet du SDK SignalRGB. Les datagrammes restent sous 5 KiB. Le pont assemble uniquement l'image la plus récente, abandonne un assemblage après 250 ms, puis valide le type JPEG et ses dimensions exactes avant de la composer.

Le bail de deux secondes restaure le fond normal après interruption du flux. Un média HTTP peut prendre temporairement priorité ; le Canvas reprend ensuite. Une seule notification Qt est en attente, et les nouvelles images remplacent les anciennes au lieu de s'accumuler.

## Vérification reproductible

```text
node test_signalrgb_background.cjs
node test_background_layout.cjs
node test_background_pacing.cjs background-core.js
python -m unittest -v test_background_api.py test_canvas_transport.py test_install_signalrgb_background.py test_media_frames.py
```

Les seize tests du client couvrent l'extraction unique, la fragmentation compacte et ses limites, la cadence, le mode Forced, la rotation du socket, l'identité, les erreurs et l'absence d'accès HID/USB. Les douze tests d'installation couvrent notamment QML, jetons, sauvegardes, chemins OneDrive et conservation d'une modification concurrente. Les tests du récepteur utilisent de vrais JPEG avec plusieurs couleurs dans une touche. Les E/S matérielles sont simulées.

## Sources

- [SignalRGB : communication réseau](https://docs.signalrgb.com/developer/plugins/advanced-communication/) décrit les sockets UDP et leur destination explicite.
- [SignalRGB : exports des plugins](https://docs.signalrgb.com/developer/plugins/plugin-exports/) décrit Size, DefaultPosition et DefaultScale.
- Le plugin historique utilisateur Streamdeck-0x0080.js appelait déjà `device.getImageBuffer` en mode Canvas. L'analyse statique de SignalRGB 2.5.77 confirme les bornes, l'extraction native et la surcharge UDP chaîne UTF-8. Voir `full-canvas-design.md` pour les empreintes et adresses relatives de cette preuve.

La composition du fond Elgato reste une instrumentation locale liée à Stream Deck 7.5.1.22901. Elle n'est pas une API officielle Elgato et ne revendique pas le support d'autres versions.
