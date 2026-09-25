# Pysyvä demo ilman maksullista palvelupakettia

## Käytössä oleva demo

- Sivusto: https://kontturi-sisallonhallinta.onrender.com/
- Sisällönhallinta: https://kontturi-sisallonhallinta.onrender.com/admin/

Demo on julkaistu erilliseen Kontturi-työtilaan Renderin Free-palveluna.
Tatu ja Niina käyttävät aiempia henkilökohtaisia tunnuksiaan ja salasanojaan;
molemmilla on pääkäyttäjän oikeudet. Tunnuksia ei säilytetä tässä repossa.
Julkaistu muutos päivittyy avoimelle demosivulle tavallisesti noin 15 sekunnissa.
Luonnos ei näy julkisella sivulla.

Paikallinen Cloudflare-demo on pysäytetty. Näiden osoitteiden käyttö ei vaadi
esittelykonetta, tunnelia tai paikallisen käynnistysskriptin suorittamista.
Älä käynnistä vanhaa demoa pilvidemon päivittämiseksi: sillä olisi erillinen,
siirtohetkeen jäänyt tietokanta. Pilvidemon sisältöä muokataan yllä olevassa
sisällönhallinnassa. Koodimuutokset julkaistaan Renderiin erikseen; automaattiset
Git-julkaisut on poistettu käytöstä.

## Kokoonpano

Kokoonpano on Render Free (Django/Wagtail) ja Neon Free (PostgreSQL sekä
yksityinen S3-yhteensopiva kuvatallennus Frankfurtissa). `render.yaml` luo vain
yhden ilmaisen verkkopalvelun. Siinä ei ole Render-tietokantaa tai maksullista levyä.
Tietokanta ja kuvat ovat palvelimesta erillään, joten ne säilyvät Renderin
uudelleenkäynnistyksissä. Julkinen sivusto ja `/admin/` käyttävät saman palvelun
pysyvää `onrender.com`-osoitetta. Nykyisiä satunnaisia Cloudflare-linkkejä ei voi
muuttaa pysyviksi eikä ohjata uuteen osoitteeseen tunnelin lakattua toimimasta.

## Käyttörajat ja nollabudjetti

- Käytä erillistä Render Hobby -työtilaa **ilman maksutapaa**. Ilmainen
  palvelin ei yksin estä laskutusta: jos työtilalla on maksutapa, liikenteen
  tai rakentamisminuuttien ylityksistä voi tulla maksuja. Älä muuta muiden
  projektien laskutusta tätä varten.
- Render Free menee lepotilaan 15 minuutin käyttötauon jälkeen. Seuraava
  avaus voi kestää noin minuutin. Tämä ei vaihda osoitetta eikä vaadi omaa
  läppäriä. Älä lisää jatkuvia herättelypyyntöjä kiertämään ilmaistason rajoja.
- Neon-projektin organisaation täytyy olla Free. Älä ota käyttöön maksullista
  tilausta tai automaattista päivitystä. Ilmaistasolla resurssirajan täyttyminen
  voi pysäyttää palvelun; sitä ei pidä kuvata taatuksi tuotantopalveluksi.
- Renderin ilmainen PostgreSQL vanhenee 30 päivässä, joten sitä ei käytetä.

Lähteet: [Render Free](https://render.com/docs/free),
[Renderin liikennelaskutus](https://render.com/docs/outbound-bandwidth),
[Neon Free](https://neon.com/pricing),
[Neonin kuvatallennus](https://neon.com/docs/storage/overview).

## Käyttöönotto

1. Valtuuta Render CLI selaimessa ja valitse maksukortiton Hobby-työtila.
2. Valtuuta Neon CLI. Tarkista organisaation Free-tila, luo PostgreSQL 17
   -projekti alueelle `aws-eu-central-1` ja yksityinen `kontturi-media`-bucket.
   Luo vain tämän projektin haaralle storage:read/storage:write-tunnus.
3. Täytä `render.yaml`-tiedoston salaiset arvot Renderin ympäristömuuttujiin.
   Luo `DJANGO_SECRET_KEY` vähintään 50 merkkiä pitkänä satunnaisarvona;
   Renderin `generateValue`-oletus on tähän tarkistukseen liian lyhyt.
   PostgreSQL-yhteyden on käytettävä TLS:ää. Tallennuksen päätepisteen on
   käytettävä HTTPS:ää. Älä lisää salaisia arvoja GitHubiin.
4. Pidä `KONTTURI_ENV=staging`: tämä säilyttää sovitun salasanakirjautumisen
   ja pitää sivuston poissa hakukoneista. `production` vaatii edelleen MFA:n.
5. Luo tuore yksityinen siirtopaketti, kun vanhan demon muokkaaminen on
   keskeytetty:

   ```powershell
   .\.venv\Scripts\python.exe scripts/export_shared_demo.py --output backend/.local/hosting/cutover-snapshot.zip
   ```

   Paketti sisältää sivut, artikkelit, kuvat, käyttäjät, salasanojen tiivisteet
   ja historiatiedot. Se ei sisällä vanhoja kirjautumisistuntoja tai selväkielisiä
   salasanoja. Säilytä paketti yksityisenä. Viennissä käytetään SQLite-varmistusta,
   eikä alkuperäistä tietokantaa muokata. Poistettujen käyttäjien/sivujen
   historiaviitteet säilyvät ilman virheellistä uudelleenluontia.
6. Aja `migrate --noinput` ja `import_site_snapshot <paketti>` paikallisella
   ylläpitokoneella, jonka prosessiympäristö osoittaa uuteen Neon-tietokantaan
   ja uuteen bucketiin. Tuonti hyväksyy vain tyhjän staging-kohteen; se tarkistaa
   tiedostopolut ja tarkistussummat sekä säilyttää käyttäjien salasanat ja roolit.
   Tiedot lähetetään tietokantaan ja kuvatallennukseen, ei Renderin väliaikaiselle
   levylle. Free-palvelun SSH:ta ei tarvita eikä se ole saatavilla.
7. Pushaa testattu koodi haaraan `feat/managed-cms`, luo Renderin **Free**-
   verkkopalvelu ja käytä komentoa `python /app/scripts/start_render.py`.
   `KONTTURI_MIGRATION_PENDING=1` tarjoaa vain huoltotilan ja terveystarkistuksen.
   Vaihda arvoon `0` vasta onnistuneen tuonnin jälkeen. Käynnistin asettaa
   Wagtailin osoitteen Renderin antamaan palveluosoitteeseen.
8. Tarkista julkiset sivut, molempien pääkäyttäjien kirjautuminen, kuvan lisäys,
   luonnoksen yksityisyys ja julkaistun muutoksen näkyminen. Käynnistä palvelu
   uudelleen ja tarkista, että tiedot ja kuvat säilyvät. Pysäytä sitten vanha
   läppärillä ajettava demo, jotta muokkaukset eivät hajaannu kahteen kantaan.
9. Lähetä uusi pysyvä osoite Tatulle ja Niinalle. Osoite säilyy, kun palvelua
   ei poisteta tai nimetä uudelleen. Pidä erilliset varmuuskopiot; ilmaistaso
   ja historiatiedot eivät yksin korvaa varmistuksia.

Renderin HTTPS-reuna ohjaa HTTP:n HTTPS:ään. Waitress käyttää palvelun sisällä
HTTPS-skeemaa hyväksymättä asiakkaan lähettämiä forwarded-otsakkeita.
Kuvat tarjoillaan saman sivuston `/media/`-osoitteista: bucket ja tallennuksen
tunnukset eivät tule selaimelle. Vain kuville sallitut polut ja tiedostotyypit
ovat julkisesti luettavissa.
