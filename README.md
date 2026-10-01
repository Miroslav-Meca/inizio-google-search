# Přirozené výsledky Google

Webová aplikace, která přijme klíčovou frázi, zobrazí přirozené výsledky Google a umožní jejich export do JSON nebo CSV.

## Aktivní vyhledávací provider

Aktivní vyhledávací cestou je **SerpApi**. Backend volá [Google Search Api služby SerpApi](https://serpapi.com/search-api) a z odpovědi zpracuje pouze pole `organic_results`. Reklamy, nákupy, mapy, knowledge graph a další bloky nepředává do výsledků. Při chybě SerpApi aplikace vrátí chybu; nepřepíná na přímý Google.

SerpApi je aktivní proto, že přímý HTTP request na Google při praktickém ověření vracel sice HTTP 200, ale místo výsledkové stránky obsah s indikátory `SG_REL` a `SG_SS`. Stejný problém byl pozorován také z lokálního Linuxu. Ochranu neobcházíme.

Přímá experimentální varianta zůstává v `app/services/google_client.py`, `google_parser.py` a `google_search.py`. Zachovány jsou také lokální HTML fixture a unit testy. Tato varianta není výchozí provider aplikace.

## Architektura a technologie

- Python a FastAPI poskytují stránku a endpoint `GET /api/search`.
- `SerpApiSearchService` v `app/services/search.py` komunikuje přes HTTPX se SerpApi.
- `app/models.py` obsahuje sdílený model výsledku (`position`, `title`, `url`, `snippet`).
- Frontend tvoří HTML, CSS a vanilla JavaScript. Výsledky vkládá jako text; odkazy přijímá pouze s HTTP(S) schématem.
- JSON odpověď má tvar `{"query":"…","results":[...]}`. CSV je dostupné přes `?format=csv`.
- FastAPI vrací `422` pro neplatný dotaz, `503` při chybějícím API klíči a `502` při chybě poskytovatele.

Výchozí parametry aktivního SerpApi vyhledávání jsou lokalita `Prague, Czechia`, jazyk `cs`, země `cz` a nejvýše 10 výsledků. Lze je změnit backendovými proměnnými `SERPAPI_LOCATION`, `SERPAPI_LANGUAGE` a `SERPAPI_COUNTRY`. Text ve formuláři je statický a uvádí Prahu a češtinu; při změně proměnných se automaticky nezmění. Experimentální přímý Google klient má `hl=cs`, `gl=cz` a počet 10 nastavený v kódu.

## Požadavky a ověřené prostředí

- Lokální instalace a testy byly spuštěny s Pythonem **3.9.10**.
- Dockerfile používá image `python:3.12-slim`. Docker Compose byl vyzkoušen manuálně, běh kontejneru se v tomto pracovním prostředí samostatně neopakuje.
- Docker Compose konfigurace byla ověřena příkazem `docker compose config -q`.
- Manuálně se ověřilo živé vyhledávání přes SerpApi. Pro stejný dotaz získal výsledky odpovídající Google Search bez reklamních a dalších nepřirozených bloků. Tento živý request nebyl proveden ani nezávisle kontrolován v rámci projektových testů.
- Veřejné nasazení nebylo provedeno; plánuje se provést samostatně mimo toto prostředí.

Závislosti jsou v `requirements.txt`. Frontendové soubory jsou v `app/static/`.

## Lokální spuštění na Linuxu

Vytvořte virtuální prostředí a nainstalujte závislosti:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Zkopírujte vzor konfigurace a nastavte vlastní klíč:

```bash
cp .env.example .env
```

Upravte `.env` a nastavte `SERPAPI_API_KEY`. Soubor `.env` je v `.gitignore`. Klíč patří pouze do backendového prostředí; nevkládejte jej do HTML, JavaScriptu ani repozitáře.

Spusťte aplikaci:

```bash
uvicorn app.main:app --reload --env-file .env
```

Otevřete <http://127.0.0.1:8000>. Příklady API:

```text
/api/search?q=Hrabyně
/api/search?q=Hrabyně&format=csv
```

Dotaz se ořízne od okrajových mezer a může mít nejvýše 200 znaků. Bez `SERPAPI_API_KEY` stránka funguje, ale vyhledávací endpoint vrátí `503` bez volání externí služby.

## Testy

Spuštění unit testů:

```bash
pytest -q
```

Poslední ověřený běh (29. 9. 2026): **42 testů prošlo**. Testy používají mockované HTTP odpovědi a lokální Google HTML fixture. Neprovádějí skutečné požadavky na SerpApi ani Google a nepotřebují skutečný API klíč.

Při ověření projektu byly úspěšně spuštěny také:

```bash
python -m compileall -q app tests
node --check app/static/script.js
docker compose config -q
```

Tyto kontroly ověřují syntaxi Python kódu, JavaScriptu a platnost konfigurace Docker Compose.

## Docker Compose

Nastavte `SERPAPI_API_KEY` v `.env` a spusťte:

```bash
docker compose up --build
```

Aplikace bude dostupná na <http://127.0.0.1:8000>. Compose předá klíč kontejneru jako proměnnou prostředí, nikoli do frontendu. Kontejner používá Python 3.12 podle Dockerfile. Zastavení: `Ctrl+C`; případné odstranění kontejneru a sítě: `docker compose down`.

## Provider, cena a omezení

SerpApi vyžaduje účet a API klíč. Cena závisí na aktuálním tarifu, pro testovací účely stačí bezplatná verze s kvótou 250 requestů za měsíc. Před použitím ověřte [aktuální ceník SerpApi](https://serpapi.com/pricing). Aplikace žádný placený tarif sama neaktivuje.

Direct Google experiment může vrátit challenge/interstitial místo SERP nebo se rozbít při změně HTML. Aplikace tuto ochranu neobchází a tuto variantu nepoužívá jako fallback.

## Možné veřejné nasazení

Pro demonstrační nasazení lze použít Render Web Service; nastavení služby musí obsahovat tajnou proměnnou `SERPAPI_API_KEY`. Start příkaz pro platformu poskytující proměnnou `PORT`:
Aplikace je veřejně dostupná na: https://inizio-google-search-m1ku.onrender.com/

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Bezplatné služby Renderu mají limity a uspávají se po nečinnosti; před vytvořením služby ověřte aktuální [dokumentaci Render Free](https://render.com/docs/free). Nasazení vyžaduje hostingový účet a připojení zdrojového repozitáře; nebylo provedeno ani otestováno.
