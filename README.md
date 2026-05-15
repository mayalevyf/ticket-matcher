# 🧾 Ticket Matcher

Application locale de lecture de tickets/factures et de rapprochement avec un relevé bancaire.  
Fonctionne entièrement hors ligne, sur ton réseau local, sans compte ni clé API.

---

## Ce que fait l'application

1. Tu uploades une ou plusieurs photos de tickets ou factures (JPG, PNG, PDF)
2. Le modèle Qwen3-VL (en local via Ollama) extrait le montant, la TVA, la date et le nom de l'enseigne
3. Chaque résultat est sauvegardé automatiquement sur disque — tu peux reprendre à tout moment
4. Tu importes ton relevé bancaire (CSV), tu indiques quelle colonne correspond à quoi
5. L'application fait le rapprochement automatiquement et tu exportes le rapport

---

## Installation — à faire une seule fois

### 1. Télécharger et installer Ollama

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

> **Si ta carte GPU a moins de 5 Go de VRAM** (ex. Quadro T1000 4 Go), télécharge la version plus légère :
> ```
> ollama pull qwen3-vl:7b-q3_K_M
> ```
> Elle pèse ~3,4 Go et tient entièrement en VRAM, ce qui est plus rapide que la version standard en mode hybride CPU/GPU.

---

### 3. Télécharger les fichiers de l'application

Place tous ces fichiers dans le **même dossier** :

```
mon-dossier/
├── app.py
├── ocr.py
├── matcher.py
├── utils.py
└── requirements.txt
```

---

### 4. Créer l'environnement Python

Ouvre un terminal dans le dossier de l'application.

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

L'application s'ouvre dans ton navigateur à `http://localhost:8501`.

> Si Ollama ne se lance pas automatiquement, ouvre un terminal séparé et lance `ollama serve` avant de démarrer Streamlit.

---

## Utilisation

### Étape 1 — Import et extraction

- Clique sur **Parcourir** et sélectionne une ou plusieurs photos de tickets
- Formats acceptés : JPG, JPEG, PNG, PDF
- L'extraction prend 15 à 60 secondes par fichier selon ton matériel
- **Chaque résultat est sauvegardé immédiatement** dans le dossier `cache_ocr/` — si l'application plante ou que tu fermes la fenêtre, les fichiers déjà traités ne sont pas perdus
- Au prochain démarrage, les fichiers en cache sont rechargés automatiquement et les fichiers déjà traités sont ignorés si tu les uploades à nouveau

### Étape 2 — Import du relevé et mapping des colonnes

- Importe le CSV de ton relevé bancaire
- L'application affiche les colonnes détectées et un aperçu des premières lignes
- Utilise les menus déroulants pour indiquer quelle colonne correspond à la date, au montant et au libellé
- Clique sur **Valider** pour passer au rapprochement

### Étape 3 — Matching bancaire

- Le rapprochement se fait automatiquement sur le montant et la date
- Chaque ligne reçoit un statut :
  - ✅ **Trouvé** — correspondance sur le montant et la date
  - ⚠️ **Écart** — correspondance probable mais différence de date ou de montant
  - ❌ **Non trouvé** — aucune ligne correspondante dans le relevé
- Exporte le rapport en CSV ou Excel

---

## Vérifier que le GPU est utilisé

Dans la barre latérale gauche, clique sur **🔍 Vérifier GPU**.

- Si le modèle n'est pas encore chargé, fais d'abord un premier appel OCR puis clique à nouveau
- Si le GPU est détecté mais que le modèle tourne sur CPU, relance `ollama serve` dans un terminal et vérifie que la ligne `CUDA device` apparaît au démarrage

---

## Cache OCR

Les résultats d'extraction sont sauvegardés dans `cache_ocr/` (un fichier JSON par ticket).  
Pour repartir de zéro, clique sur **🗑️ Vider le cache** dans la barre latérale.

---

## Format du relevé bancaire

Le fichier doit être au format CSV avec au minimum une colonne date, une colonne montant et une colonne libellé. Les exports des banques françaises (Crédit Agricole, BNP, Société Générale…) sont compatibles directement.

Si ta banque exporte en XLS ou XLSX, ouvre-le dans Excel et enregistre-le en CSV.

---

## Problèmes fréquents

**Ollama ne répond pas**  
Lance `ollama serve` dans un terminal séparé avant de démarrer l'application.

**Le modèle est lent au premier ticket**  
Normal — le modèle (~5 Go) se charge en mémoire. Attends 30 à 60 secondes après le premier upload.

**Le GPU n'est pas utilisé malgré une carte NVIDIA**  
Vérifie que la version d'Ollama installée inclut le support CUDA : au démarrage de `ollama serve`, la ligne `CUDA device` doit apparaître. Si ce n'est pas le cas, réinstalle depuis [https://ollama.com/download](https://ollama.com/download).

**Erreur à l'activation du venv sous PowerShell**  
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Puis relance `.venv\Scripts\activate`.
