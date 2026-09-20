# Client Canvas complet — version 0.2

Le client `SignalRGB_StreamDeck_Background.js` capture une image du Canvas, au lieu de quinze couleurs uniformes. Il utilise le récepteur `canvas_transport.py` et l'API locale. La validation réelle coordonnée par l'agent principal a réussi : l'utilisateur a confirmé les dégradés et la fluidité ; le relevé final compte 1 383 images, quinze touches avec du détail spatial, 17 acquittements/s pour une cible de 20 et aucune erreur. Les étapes statiques et tests simulés détaillés ci-dessous restent distincts de cette validation matérielle.

**Évolution 0.2.1, 20 septembre 2026 :** le document ci-dessous conserve l'analyse et les mesures historiques en 320×200. La largeur source est désormais réglable de 16 à 320 via `CanvasWidth`, avec 32×20 par défaut et une boîte 33×21. La sortie JPEG reste 480×272, mais le nombre d'échantillons source diminue lorsque le layout est compact. Voir [SIGNALRGB-INTEGRATION.md](SIGNALRGB-INTEGRATION.md) pour le réglage actuel et ses limites. L'identité, le transport et le hook Elgato ne changent pas.

## API native vérifiée

Le fichier historique utilisateur `%USERPROFILE%\OneDrive\Documents\WhirlwindFX\Plugins\Streamdeck-0x0080.js`, ligne 176, utilisait déjà `device.getImageBuffer(x,y,width,height,options)` en mode Canvas. Les options comprenaient `outputWidth`, `outputHeight`, `flipV`, `flipH`. Le plugin Corsair Nexus installé cite `format:"BMP"` dans sa fonction `colorgrabber` (non appelée par son Render actuel) : cet exemple établit une signature, pas son fonctionnement matériel présent.

L'examen statique de SignalRGB 2.5.77 confirme cette API dans les métadonnées Qt. Exécutable SHA256 : `dde18ae63ee3451f72050e42874fbcfec26787fc4cebd6235a0fb6acfc086405`.

- Fonction `getImageBuffer` : RVA `0x015df400` à `0x015e0415`.
- Les comparaisons aux RVA `0x015dfa77` et `0x015dfaae` refusent **x+width >= largeur** et **y+height >= hauteur**. Le contrôle est strict : `Size=[321,201]` permet le découpage `[0,0,320,200]` ; `Size=[320,200]` le refuserait.
- La sortie est limitée à 1–1024 sur chaque axe.
- Le chemin emploie `QPainter::drawImage` depuis le tampon image du périphérique (`this+0x7e8`), puis encode l'image. Il n'effectue pas de boucle d'appels JavaScript `device.color`.
- Les appels de l'ancien plugin et les chaînes du binaire étayent JPEG/BMP. Les formats bruts RGB/RGBA et la qualité configurable trouvés dans `@SignalRGB/lcd` appartiennent à un module LCD distinct. Ils ne sont pas supposés disponibles dans `device.getImageBuffer`.

L'analyse historique a employé `inspect-signal-image-api.py` et `disassemble-image-buffer.py`. Ces scripts d'investigation et leurs sorties ne sont pas redistribués dans ce dépôt ; les adresses et le hash ci-dessus identifient la version examinée. Aucune instrumentation du processus SignalRGB n'était nécessaire pour ces lectures.

La [documentation des exports SignalRGB](https://docs.signalrgb.com/developer/plugins/plugin-exports/) définit Size, DefaultPosition et DefaultScale. Le [cycle de vie officiel](https://docs.signalrgb.com/developer/plugins/) décrit l'alimentation du tampon des pixels avant Render. Les recherches dans la documentation publique n'ont pas trouvé de page décrivant `getImageBuffer` ; la preuve précise de son contrat provient ici des sources installées et du binaire, pas d'une documentation publique inventée.

## Géométrie et transport

Le contrôleur porte une nouvelle identité, `streamdeck-background-canvas-v2`, pour recevoir les défauts origine `[0,0]`, échelle `1`. Il n'hérite donc pas de l'échelle `8` du contrôleur expérimental de quinze couleurs. `Validate` refuse l'ancienne identité. Aucun réglage utilisateur n'est écrit directement dans le registre. Les quinze centres LED restent uniquement des repères de disposition : leurs coordonnées suivent les centres des touches physiques, convertis en coordonnées source.

Une trame Canvas fait **un appel** `getImageBuffer(0,0,320,200,{outputWidth:480,outputHeight:272,format:"JPEG",flipV:false,flipH:false})`. Le résultat conserve le détail spatial à l'intérieur de chaque touche. Le redimensionnement et la compression JPEG ne constituent pas une copie sans perte des pixels d'origine.

L'image est divisée en fragments de 1 024 octets au maximum, vers `127.0.0.1:47685` uniquement :

```javascript
{token, kind:"canvas-jpeg", frame, part, total, data:[/* octets */], lease_ms:2000}
```

Limites : JPEG de 256 KiB, 256 fragments maximum, identifiant entier croissant dans la plage sûre JavaScript. Le destinataire assemble la trame la plus récente puis valide son JPEG et ses dimensions avant de découper les quinze tuiles selon la disposition native. Le mode Forced conserve quinze couleurs identiques ; Canvas n'utilise jamais ce chemin en cas d'échec.

Le premier essai a révélé un défaut de transport : passer l'objet directement à `socket.write` déclenche une sérialisation JSON indentée qui grossit fortement les tableaux d'octets. La réception bornée à 21 000 octets a alors levé Windows `WSAEMSGSIZE` (10040). La version corrigée envoie **`JSON.stringify(packet)`**, donc une chaîne compacte. L'analyse de `PluginUdpSocket::write` (RVA `0x018d1780`) prouve deux chemins distincts : `isString` à `0x018d19cf`, conversion directe `QString::toUtf8` à `0x018d19f0`, puis `writeDatagram` ; pour un objet, `QJsonDocument::toJson` avec le format zéro à `0x018d1a99`. Le script d'investigation historique `disassemble-udp-write.py` n'est pas redistribué. Les fragments compacts de 1 024 octets restent sous 5 KiB avec leurs métadonnées.

La garde de `Initialize` refuse également de créer un socket pour l'ancienne identité, même si un rechargement du renderer ne rappelle pas `Validate`. Elle journalise l'identité et la valeur FPS réellement reçues. Un ancien moteur déjà chargé avec une version précédente doit être rechargé ou arrêté pour adopter cette garde ; le seul changement du fichier n'est pas considéré comme une preuve que le service de découverte a redémarré.

## Cadence et vérification

Le client propose 20 émissions/s par défaut, réglables de 1 à 30. Il demande un cycle de rendu de 10 ms et une cible moteur de 60 Hz, puis limite ses captures par une horloge sans pause bloquante. Ce sont des plafonds demandés, pas une mesure de rafraîchissement optique. Les erreurs sont également limitées dans le temps et leurs messages n'incluent aucun jeton ni paquet.

Les seize tests JavaScript vérifient l'extraction unique, ses bornes, la reconstruction exacte des octets fragmentés, le maximum 256 fragments compacts, la cadence, l'identité, le refus de l'ancien renderer, les erreurs, l'absence de repli monochrome et l'absence d'accès HID/USB. Les douze tests de l'installateur passent avec le modèle 0.2 et son interface QML. Ils exécutent des E/S simulées ; le test du récepteur Python emploie séparément de vrais JPEG pour vérifier le détail spatial.
