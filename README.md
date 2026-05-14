# 🧾 Ticket Matcher

Application locale de lecture de tickets/factures et de rapprochement avec un relevé bancaire.  
Fonctionne entièrement hors ligne, sur ton réseau local, sans compte ni clé API.

---

## Ce que fait l'application

1. Tu uploades une photo de ticket, facture ou reçu
2. Le modèle Qwen3-VL (en local) en extrait le montant, la date et le nom de l'enseigne
3. Tu vérifies et corriges les données dans un tableau éditable
4. Tu exportes un CSV propre
5. Tu importes ton relevé bancaire et l'application fait le rapprochement automatiquement

---

## Installation — à faire une seule fois

### 1. Télécharger et installer Ollama

Ollama fait tourner le modèle d'IA en local sur ton ordinateur.

👉 [https://ollama.com/download](https://ollama.com/download)

Télécharge l'installeur pour ton système (Windows, macOS ou Linux) et lance-le.  
Une fois installé, Ollama apparaît dans la barre des tâches et démarre automatiquement avec Windows.

---

### 2. Télécharger le modèle Qwen3-VL

Ouvre un terminal et lance :

```
ollama run qwen3-vl
```

Le téléchargement prend quelques minutes (~5 Go). Une barre de progression s'affiche.  
Une fois terminé, tu peux fermer le terminal avec `Ctrl + C`.

---

### 3. Télécharger les fichiers de l'application

Télécharge les fichiers suivants et place-les tous dans le **même dossier** :

```
mon-dossier/
├── app.py
├── ocr.py
├── matcher.py
├── utils.py
├── requirements.txt
└── .streamlit/
    └── config.toml
```

---

### 4. Créer l'environnement Python

Ouvre un terminal dans le dossier de l'application et lance ces commandes une par une :

**Créer l'environnement :**
```
python -m venv .venv
```

**L'activer — macOS / Linux :**
```
source .venv/bin/activate
```

**L'activer — Windows (Invite de commandes) :**
```
.venv\Scripts\activate.bat
```

**L'activer — Windows (PowerShell) :**
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.venv\Scripts\activate
```

**Installer les dépendances :**
```
pip install -r requirements.txt
```

---

## Lancer l'application

Chaque fois que tu veux utiliser l'application, dans le terminal (environnement activé) :

```
streamlit run app.py
```

L'application s'ouvre automatiquement dans ton navigateur à l'adresse `http://localhost:8501`.

> Ollama se lance automatiquement en arrière-plan au démarrage de Windows.  
> Si ce n'est pas le cas, ouvre un terminal séparé et lance `ollama serve` avant de démarrer Streamlit.

---

## Accès depuis un autre appareil du réseau

L'application est accessible depuis n'importe quel appareil connecté au même Wi-Fi.

**Trouver l'adresse IP du PC hôte :**

- Windows : ouvre un terminal et tape `ipconfig` → cherche "Adresse IPv4"
- macOS : `ipconfig getifaddr en0`
- Linux : `hostname -I`

Sur l'autre appareil, ouvre un navigateur et va sur :
```
http://<adresse-ip>:8501
```

---

## Utilisation

### Étape 1 — Import et extraction

- Clique sur **Parcourir** et sélectionne une ou plusieurs photos de tickets
- Formats acceptés : JPG, JPEG, PNG, WEBP, PDF
- L'extraction prend 15 à 45 secondes par photo selon ton matériel
- Le résultat s'affiche à droite de chaque photo

### Étape 2 — Vérification

- Les données extraites apparaissent dans un tableau éditable
- Clique directement sur une cellule pour corriger une valeur
- Clique sur **Exporter le CSV** pour sauvegarder les données

### Étape 3 — Matching bancaire

- Importe le CSV de ton relevé bancaire (téléchargeable depuis l'espace client de ta banque)
- L'application détecte automatiquement les colonnes date, montant et libellé
- Le rapprochement se fait sur le montant et la date
- Chaque ligne reçoit un statut :
  - ✅ **Trouvé** — correspondance sur le montant et la date
  - ⚠️ **Écart** — correspondance probable mais différence de date ou montant
  - ❌ **Non trouvé** — aucune ligne correspondante dans le relevé
- Exporte le rapport final en CSV ou Excel

---

## Format du relevé bancaire

Le fichier CSV doit contenir au minimum une colonne date, une colonne montant et une colonne libellé.  
Les exports des banques françaises (Crédit Agricole, BNP, Société Générale…) sont compatibles directement.

---

## Problèmes fréquents

**Ollama ne répond pas**

Lance `ollama serve` dans un terminal séparé avant de démarrer l'application.

---

**Le modèle est lent au premier lancement**

Normal — le modèle (5 Go) se charge en mémoire. Attends 30 à 60 secondes après le premier upload avant de voir une réponse.

---

**Erreur à l'activation du venv sous PowerShell**

```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Puis relance `.venv\Scripts\activate`.

---

**Le relevé bancaire n'est pas reconnu**

Vérifie que le fichier est bien au format CSV. Si ta banque exporte en XLS ou XLSX, ouvre-le dans Excel et enregistre-le en CSV (séparateur point-virgule).
