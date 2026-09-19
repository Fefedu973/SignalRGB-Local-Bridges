# Stream Deck : fonds animés, images et API publiques

Recherche en lecture seule du **19 septembre 2026**, limitée aux sources Elgato officielles. Aucun profil utilisateur, périphérique, plugin installé ou réglage n’a été modifié par cette recherche. Les possibilités ci-dessous ne sont pas des résultats de test sur le Stream Deck de l’utilisateur.

## Conclusion utile pour l’implémentation

Le **fond natif de page** est bien une couche distincte derrière les icônes transparentes et les titres. C’est la surface qui correspond au besoin de conserver les actions et leur affichage. Elle est documentée dans l’application, mais **aucune commande publique pour la modifier en temps réel n’a été trouvée dans le SDK ou son protocole WebSocket actuel**.

Le SDK `setImage` sert à remplacer l’image d’une action appartenant au plugin. Il n’est donc pas un moteur de fond global compatible avec les actions existantes. Un flux SignalRGB externe résoudrait la source de couleurs, mais pas cette limite du destinataire Elgato.

Une animation native de fond de page, GIF ou vidéo, reste **non établie par les sources officielles consultées**. Les GIF sont explicitement documentés pour les icônes personnalisées et les écrans de veille ; ce sont deux autres surfaces. Il ne faut pas promettre que l’acceptation d’un GIF dans une boîte de dialogue signifie qu’il est joué comme fond animé.

## Versions réellement consultées

- L’[index officiel des releases](https://help.elgato.com/hc/en-us/sections/5162671529357-Elgato-Stream-Deck-Software-Release-Notes) affichait **7.5.1** en tête. La [7.5.1 du 28 juillet 2026](https://help.elgato.com/hc/en-us/articles/49238316077713-Elgato-Stream-Deck-7-5-1-Release-Notes) concerne des corrections ; la [7.5.0 du 30 juin 2026](https://help.elgato.com/hc/en-us/articles/48328697898897-Elgato-Stream-Deck-7-5-0-Release-Notes) ajoute surtout NIGHTSWORD et des correctifs. Aucune n’annonce de flux de fond de page.
- La [référence WebSocket](https://docs.elgato.com/streamdeck/sdk/references/websocket/plugin/) et les guides affichent « Version 2.0.0 » ; le dépôt officiel est plus récent : **`@elgato/streamdeck` 2.1.2**, commit [`55be0439aeca2fcdf6babd2d23eb30780638ed85`](https://github.com/elgatosf/streamdeck/commit/55be0439aeca2fcdf6babd2d23eb30780638ed85), daté du **19 août 2026**. Le commit lié identifie précisément la source consultée ; le SDK tiers n’est pas redistribué ici.
- Le [CHANGELOG du SDK à ce commit](https://github.com/elgatosf/streamdeck/blob/55be0439aeca2fcdf6babd2d23eb30780638ed85/packages/plugin/CHANGELOG.md) décrit notamment le cache des paramètres et les ressources embarquées. La recherche `background`, `wallpaper`, `animated`, `animation` dans le code du package n’a trouvé aucun contrôleur de fond de page ; les occurrences `background` du code concernent surtout les couleurs de l’interface dans les informations d’enregistrement. La référence de manifest traite séparément le fond de la bande tactile.

## Les surfaces à distinguer

| Surface | Ce qui est officiellement documenté | Répond au besoin exact ? |
|---|---|---|
| Fond de page de l’application | Image commune derrière icônes transparentes et textes ; défaut de profil et remplacement par page/dossier | **Oui pour un fond statique**. Flux animé externe non documenté. |
| Icône personnalisée par l’utilisateur | GIF et WebP animés, entre autres formats | Conserve l’action mais **remplace son image personnalisée**. Ne conserve pas automatiquement les icônes dynamiques du plugin. |
| Image d’action via `setImage` | SVG, JPEG, PNG, WebP fixes ; fichier ou data URL ; cible matériel/logiciel | Remplace l’image de l’action gérée par le plugin. Pas de GIF animé dans cette méthode. |
| Écran de veille | Image ou GIF animé à partir de Stream Deck 6.6, selon le modèle | Affichage de veille, pas un fond pendant l’utilisation des boutons. |
| Écran de démarrage / standby | Image lorsque le matériel démarre ou n’est pas relié à l’application | Pas un fond actif. |
| Bande tactile d’un Stream Deck + | Layout de l’action avec images, textes, ordre et opacité ; fond de manifest | Possible composition dans **son propre layout**, pas sous les boutons ni sous les layouts d’autres plugins. |
| API USB HID | Images JPEG de touche ou d’écran ; certaines familles ont des commandes nommées Background | Transport d’images, pas de contrat de composition alpha avec le rendu de l’application. |

### Fond natif de page

Les [release notes 6.6, 18 avril 2024](https://help.elgato.com/hc/en-us/articles/26005306818701-Elgato-Stream-Deck-6-6-Release-Notes) introduisent le fond couvrant les touches d’une page, sous les icônes transparentes et le texte. Le fond courant peut devenir le défaut du profil ; les pages et dossiers conservent leurs remplacements. Le même document décrit séparément les écrans de veille GIF et l’image de standby. Il ne présente pas le fond actif comme un lecteur vidéo ou GIF. Les [notes de bêta 6.6](https://help.elgato.com/hc/en-us/articles/25430103180557-Stream-Deck-6-6-Beta-Changelog) mentionnent la sélection d’une image précise d’un GIF dans l’outil de recadrage : c’est cohérent avec un import statique, sans suffire seul à caractériser chaque version actuelle.

Conséquence graphique : une icône opaque cache le fond sous ses pixels. Une icône transparente permet de le voir. Aucun réglage de fond ne rend automatiquement transparent un visuel opaque ; le remplacer pour découper ses contours contredirait la contrainte stricte de ne pas toucher aux icônes.

### Icônes et `setImage`

L’[aide de personnalisation des icônes](https://help.elgato.com/hc/en-us/articles/360028237271-Elgato-Stream-Deck-Customizing-Key-Icons) accepte notamment PNG, JPEG, GIF, BMP, WebP et WebP animé. C’est une modification de l’icône d’une touche, même lorsqu’on y dessine une portion d’un grand fond.

Le [guide Keys du SDK](https://docs.elgato.com/streamdeck/sdk/guides/keys/) limite `setImage` aux images fixes et donne l’ordre de priorité : image utilisateur, image définie par le plugin, image de manifest. Une icône utilisateur prend donc le dessus sur les mises à jour du plugin. La fonction vise une instance d’action ; le choix `Target.Hardware` ne crée pas une couche de fond. La référence ne propose aucun `getImage` qui retournerait l’image finale composée de chaque action pour la conserver et la recomposer automatiquement.

Le [code `KeyAction.setImage` au commit consulté](https://github.com/elgatosf/streamdeck/blob/55be0439aeca2fcdf6babd2d23eb30780638ed85/packages/plugin/src/plugin/actions/key.ts) confirme un message `setImage` avec `context: this.id`. Ses commentaires explicitent la priorité de l’image choisie par l’utilisateur. Répéter des images fixes peut servir à l’animation **dans une action créée pour cela**, avec un débit à mesurer ; ce n’est pas une API de décoration globale.

### Bande tactile

Le [guide Dials & Touch Strip](https://docs.elgato.com/streamdeck/sdk/guides/dials/) documente des layouts de **200 × 100** par action, dont `full-canvas`, et des mises à jour `setFeedback`. Le [schéma de layout](https://docs.elgato.com/streamdeck/sdk/references/touch-strip-layout/) permet les éléments pixmap/texte, `zOrder`, opacité et couleurs de fond. Un plugin peut donc dessiner un arrière-plan et son propre premier plan dans cet espace.

Le [manifest](https://docs.elgato.com/streamdeck/sdk/references/manifest/) propose `Actions[].Encoder.background`, image PNG/SVG en 200 × 100 et 400 × 200. Cette propriété concerne une action de type Encoder et peut être remplacée par l’utilisateur. Ce n’est pas le wallpaper des touches ni une méthode publique de remplacement du fond de toute la bande en conservant les autres actions.

## API externe : portée exacte

### WebSocket du SDK

Le [protocole de plugin officiel](https://docs.elgato.com/streamdeck/sdk/references/websocket/plugin/) est une connexion entre un plugin et l’application. Le port, l’UUID d’enregistrement et l’événement de registration sont passés au lancement. Les commandes d’image et de feedback ciblent des `context` d’actions ; ces contextes ne sont pas des identifiants externes persistants. La liste de commandes ne contient ni `setPageBackground`, ni `setWallpaper`, ni un flux global du canvas. `switchToProfile` est lui-même limité aux profils distribués avec le plugin.

Un service externe pourrait communiquer avec **un plugin que nous possédons** par un serveur local explicitement implémenté, puis ce plugin pourrait utiliser ses actions. Cette architecture est une possibilité de développement, pas une API Elgato déjà disponible pour piloter tous les pixels de toutes les actions. Le [modèle d’exécution officiel](https://docs.elgato.com/streamdeck/sdk/introduction/plugin-environment/) place la communication avec le matériel dans l’application Stream Deck.

### Deep links et MCP

Le [deep-linking officiel](https://docs.elgato.com/streamdeck/sdk/guides/deep-linking/) permet d’envoyer un message à un plugin via `streamdeck://plugins/message/<PLUGIN_UUID>/...`; le mode passif existe depuis 7.0. C’est une surface de commande utile pour une configuration ou un déclenchement, pas un transport documenté d’images vidéo à haute fréquence.

Le [MCP Elgato](https://www.elgato.com/ww/en/explorer/products/stream-deck/sd-mcp-setup/), document mis à jour le **9 juillet 2026**, apparaît avec Stream Deck 7.4. Il expose les actions volontairement placées dans un profil distinct « MCP Actions » ; les autres profils restent hors de ce périmètre. Il sert à déclencher les actions et n’apporte dans cette documentation aucune API de fond ou de lecture du canvas. Le serveur officiel se nomme `@elgato/mcp-server`. Il n’a pas été installé ni lancé pour cette recherche.

## USB HID : vraie piste documentée, composition non démontrée

Elgato publie maintenant une [API HID officielle](https://docs.elgato.com/streamdeck/hid/intro/). La [référence générale](https://docs.elgato.com/streamdeck/hid/general/) décrit les rapports, les touches, les images et la luminosité. Les images des familles modernes sont converties en **JPEG**, puis fragmentées en rapports Output ; le format transporté ne contient donc pas de canal alpha utilisable comme une icône transparente.

La [famille Stream Deck XL](https://docs.elgato.com/streamdeck/hid/stream-deck-xl/) expose précisément :

| Rapport / commande | Fonction officielle |
|---|---|
| Output `02/07` | Image d’une touche |
| Output `02/08` | Image complète de l’écran |
| Output `02/0D` | Enregistrer une image de fond à un index |
| Feature `03/13` | Afficher un fond précédemment enregistré |

Le XL utilise 32 touches de 96 × 96 et un LCD de 1024 × 600 ; ces valeurs ne doivent pas être copiées vers un autre modèle. Les pages [Classic](https://docs.elgato.com/streamdeck/hid/module-15_32) et [Stream Deck +](https://docs.elgato.com/streamdeck/hid/stream-deck-plus/) ont leurs propres formats et géométries.

**Limite de preuve :** le mot Background dans les commandes HID ne documente pas une composition permanente derrière les images des touches ni une coexistence coordonnée avec l’application. La persistance, le rafraîchissement, l’effet sur les images déjà affichées et la fréquence fiable doivent être vérifiés sur le modèle exact. Cette piste mérite une lecture/capture ciblée si l’utilisateur souhaite poursuivre, mais elle ne démontre pas aujourd’hui un fond animé conservant tous les visuels et comportements gérés par Elgato.

Une écriture HID parallèle à l’application peut donner deux producteurs d’images concurrents. Une interception du rendu, un hook du processus, ou la modification continue de fichiers internes de profil serait une **intégration non documentée**, dépendante de version. Sans preuve du rechargement, de la composition et de la restauration, elle ne doit pas être présentée comme un plugin officiel propre.

## Décision technique proposée, sans promesse de résultat non testé

1. **Voie officiellement établie pour garder actions et icônes :** fond natif de page statique, visible à travers les zones transparentes.
2. **Voie officiellement établie pour afficher de l’animation :** icônes GIF personnalisées ou écran de veille ; ces surfaces ne satisfont pas la contrainte exacte d’un fond actif derrière les icônes existantes.
3. **Voie SDK pour un canvas externe :** action dédiée ou propre layout Encoder recevant des images fixes successives. Elle peut démontrer le transport SignalRGB, mais ne doit pas remplacer les actions de l’utilisateur sous prétexte de satisfaire la demande.
4. **Pour le besoin exact animé :** confirmer la surface interne du fond de page de la version installée et son éventuel mécanisme de mise à jour. Un résultat positif serait une extension expérimentale à qualifier, à côté du SDK public. L’API HID Background est une piste distincte dont la composition reste à établir.

Les sources SignalRGB et la disponibilité de son canvas sont étudiées séparément par l’autre sous-tâche. Ce rapport n’en déduit aucune API de pixels inexistante et ne fournit aucun port ou endpoint SignalRGB supposé.
