# Guide d'utilisation — VideoGen

---

## 1. Accès au tableau de bord

Vous avez reçu un **lien direct** de la forme :

```
http://...sslip.io/monitor?key=VOTRE_CLE
```

**Enregistrez ce lien dans vos favoris.** Il vous connecte automatiquement, sans saisie de mot de passe.

> Si la page demande une clé, contactez l'administrateur pour obtenir votre lien personnel.

---

## 2. Tableau de bord — Onglet Pipelines

C'est la vue principale. Elle se rafraîchit automatiquement toutes les 5 secondes.

### Les 4 compteurs en haut

| Compteur | Ce qu'il indique |
|----------|-----------------|
| **Total** | Nombre de vidéos lancées |
| **Terminés** | Vidéos prêtes à télécharger |
| **En cours** | Vidéos en cours de génération |
| **Échoués** | Vidéos ayant rencontré une erreur |

### Lire une carte de job

Chaque vidéo en cours affiche une **barre de progression** et 5 étapes :

```
🤖 Claude  →  🎙️ ElevenLabs  →  🎬 B-roll  →  ⚙️ Rendu  →  ✅ Livré
```

- **Violet pulsant** = étape en cours
- **Vert** = étape terminée
- **Rouge** = erreur sur cette étape

Quand la vidéo est prête, un bouton **"Voir la vidéo générée"** apparaît sur la carte. Il ouvre le fichier directement depuis Google Drive.

---

## 3. Tableau de bord — Onglet Voix

Cet onglet liste toutes les voix disponibles pour vos publicités.

**Utilisation :**

1. Écoutez chaque voix avec le lecteur ▶
2. Cliquez **Copier ID** sur la voix choisie
3. Collez l'ID dans la colonne **Voix (colonne F)** du Google Sheet

---

## 4. Lancer une génération depuis Google Sheets

Le Google Sheet est le point de départ de chaque vidéo.

### Colonnes à remplir avant de lancer

| Colonne | Contenu |
|---------|---------|
| A — Script | Le texte de la publicité |
| B — Statut | Laisser vide pour l'instant |
| C — Format | `9:16` (vertical) ou `16:9` (horizontal) |
| D — Stratégie | `A` (Kling seul) ou `B` (bibliothèque + Kling) |
| E — Durée | Durée souhaitée en secondes |
| F — Voix | ID de la voix (copié depuis l'onglet Voix) |
| G — Musique | URL d'un fichier audio (ou laisser vide) |
| H — CTA | Texte du call-to-action final |

### Déclencher la génération

1. Remplissez toutes les colonnes de la ligne
2. Dans la colonne **B — Statut**, saisissez **`ok`**
3. Le système démarre automatiquement dans les secondes qui suivent
4. Suivez l'avancement dans le tableau de bord

---

## 5. Récupérer la vidéo terminée

Quand le statut passe à **Terminé** (vert) :

- Cliquez le bouton **"Voir la vidéo générée"** sur la carte
- Le lien Google Drive s'ouvre — téléchargez ou partagez directement

La colonne **I — Lien output** du Google Sheet contient aussi ce lien.

---

## 6. Quand contacter l'administrateur

**Contactez-nous si vous observez l'un de ces cas :**

| Situation | Action |
|-----------|--------|
| Une carte affiche **Échoué** (rouge) | Envoyez une capture d'écran de la carte + le contenu du script |
| Une vidéo est bloquée **En cours depuis plus de 15 minutes** | Notifiez avec l'heure de lancement et l'ID du job (les 8 caractères affichés) |
| Le tableau de bord affiche **"Hors ligne"** ou **"Timeout"** | Notifiez immédiatement |
| La vidéo générée ne correspond pas au script | Décrivez précisément ce qui ne correspond pas |

**Ne relancez pas une génération** sur la même ligne sans avoir confirmé avec l'administrateur — cela consomme du crédit API.

---

## Résumé rapide

```
1. Ouvrir le lien favori
2. Remplir le Google Sheet (colonnes A à H)
3. Mettre "ok" dans la colonne B
4. Suivre dans le tableau de bord → onglet Pipelines
5. Télécharger via le bouton "Voir la vidéo générée"
```
