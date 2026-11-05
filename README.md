# MarketRadar AI

Application Flask de création d'études de marché, avec une interface Streamlit déployable, un compte utilisateur, un historique SQL et une génération de rapport par Gemini ou OpenAI.

## Déploiement pour le jury avec Streamlit Community Cloud

L’interface Streamlit réutilise le backend, les modèles SQL, la recherche Tavily et le calcul Evidence Score existants.

1. Publie le dossier du projet dans un dépôt GitHub privé ou public. Ne publie jamais `.env`, `.streamlit/secrets.toml`, `instance/` ni des clés API. Le fichier `.gitignore` les exclut.
2. Crée une base PostgreSQL en ligne (par exemple Neon) et récupère son URL de connexion avec SSL activé.
3. Sur Streamlit Community Cloud, sélectionne **Create app**, le dépôt et la branche, puis indique `streamlit_app.py` comme fichier principal. Choisis Python 3.12 si l’option est demandée.
4. Dans **Advanced settings → Secrets**, colle des secrets TOML de ce type, en remplaçant les valeurs d’exemple. Ne partage jamais les clés réelles :

   ```toml
   DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
   SECRET_KEY = "remplacer-par-une-longue-valeur-aleatoire"
   AI_PROVIDER = "gemini"
   GEMINI_API_KEY = "cle-google-ai-studio"
   GEMINI_MODEL = "gemini-3.5-flash"
   TAVILY_API_KEY = "cle-tavily"
   ```

   Pour OpenAI, utilise `AI_PROVIDER = "openai"`, `OPENAI_API_KEY` et éventuellement `OPENAI_MODEL`, et enlève ou laisse vides les secrets Gemini. Les clés des services IA et de recherche sont obligatoires pour générer les études avec recherche Web.
5. Déploie l’application et teste la création d’un compte, la génération d’une étude, l’ajout manuel d’une source et l’ouverture de l’historique. Partage ensuite l’URL Streamlit avec le jury.

L’URL `DATABASE_URL` doit être celle d’une base PostgreSQL persistante, pas SQLite. SQLite est pratique en local, mais son fichier peut être perdu lors d’un redéploiement et n’est pas adapté à plusieurs sessions hébergées. Streamlit Cloud utilise le fichier `requirements.txt` pour installer Streamlit et le pilote PostgreSQL. La première exécution crée les tables SQL automatiquement.

Pour tester Streamlit en local sous Windows :

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run streamlit_app.py
```

Le fichier `.env` local peut fournir les mêmes variables en développement. En production, configure-les dans les secrets de Streamlit Cloud.

## Démarrage sous Windows

Depuis PowerShell, dans le dossier `C:\Users\redao\market-radar-ai` :

```powershell
py -3 -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
py -3 app.py
```

Pour Gemini, collez votre clé Google AI Studio après `GEMINI_API_KEY=`. Le projet est réglé sur `AI_PROVIDER=gemini` et `GEMINI_MODEL=gemini-3.5-flash`. Enregistrez `.env`, puis redémarrez Flask. Ne partagez pas cette clé et ne publiez jamais le fichier `.env`.

Pour activer la recherche Web automatique nécessaire à l’Evidence Score, créez une clé API Tavily et renseignez `TAVILY_API_KEY=` dans `.env`. Le brief de recherche est transmis à Tavily et les extraits trouvés sont envoyés au fournisseur IA configuré. Sans clé Tavily, l’étude peut toujours être générée, mais l’application l’indique et n’invente aucune source ni aucun score.

Pour revenir à OpenAI, utilisez `AI_PROVIDER=openai` et renseignez `OPENAI_API_KEY`. Les limites gratuites Gemini peuvent changer; les données envoyées sur le niveau gratuit peuvent être utilisées pour améliorer les produits Google. N’envoyez pas de données confidentielles.

Ouvrez ensuite `http://127.0.0.1:5000`, créez un compte et soumettez un brief. Chaque rapport réussi est enregistré dans la base SQLite locale.

Vous pouvez joindre un fichier CSV ou Excel (.xlsx) de 5 Mo maximum. Un échantillon de ses données est transmis au fournisseur IA avec le brief pour contextualiser l’analyse; n’envoyez pas de données personnelles ou confidentielles. Les fichiers ne sont pas conservés après la requête.

Chaque rapport affiche un score indicatif de couverture des données (base de l’analyse IA, présence/volume du fichier et nombre de variables). Ce score n’est pas une probabilité d’exactitude. Avec Tavily activé, une recherche Web précède la génération du rapport et les sources citées proviennent des résultats de cette recherche. Les extraits, dates et classifications peuvent être incomplets ou incorrects : contrôlez les pages avant de prendre une décision.

## Evidence Score

Avec Tavily configuré, la recherche automatique alimente le rapport en résultats Web réels. L’IA associe des résultats à chaque constat et indique s’ils semblent le soutenir, le contredire ou ne pas trancher. Seuls les index renvoyés par Tavily sont acceptés; le serveur recalcule le score et ignore tout score provenant du navigateur. Les sources, critères et calculs sont conservés dans les tables SQLite `evidence_sources` et `evidence_assessments`. Vous pouvez aussi ajouter manuellement une source.

La formule initiale est `Q × 0,30 + N × 0,25 + F × 0,25 + C × 0,20`. Il s’agit d’une méthode de travail à tester et calibrer, pas d’une méthode scientifiquement validée :

- **Qualité (Q)** : autorité indicative selon le type déclaré (organisme public 95, académique 90, organisation internationale 90, étude sectorielle 75, donnée primaire d’entreprise 70, presse 60, autre 35), combinée à 70 % de cette autorité et 30 points si la méthodologie est déclarée transparente.
- **Indépendance (N)** : 25 points par origine distincte déclarée, plafonnés à 100. Les reprises d’une même publication doivent donc utiliser le même identifiant d’origine. Un score final n’est affiché qu’avec au moins deux origines indépendantes.
- **Fraîcheur (F)** : décroît linéairement de 100 à 0 selon l’âge et la durée indicative du type de donnée : prix 7 jours, tendances 90 jours, données financières 365 jours, démographiques 1 095 jours, historiques 10 ans, autre 180 jours. Une donnée dépassant cette durée déclenche un avertissement.
- **Cohérence (C)** : proportion de la position majoritaire parmi les sources qui confirment ou contredisent le constat. Les sources « ne tranche pas » n’entrent pas dans ce calcul. Des sources importantes déclarées contradictoires déclenchent un avertissement.

Les types de source sont estimés depuis le domaine Web. Les dates, positions et transparence méthodologique peuvent manquer ou être mal identifiées; une date absente donne une fraîcheur de zéro et un avertissement, jamais une date inventée. L’indépendance automatique est estimée par domaine : des reprises d’une source originale sur différents domaines peuvent ne pas être détectées. En l’absence de deux origines/domaines ou de position exploitable, aucun score final n’est affiché. Consultez les sources et leurs périmètres avant toute décision.

## Tests

```powershell
py -3 -m pytest tests/test_app.py -q
```