"""Génère les données fictives du SAV : manuel PDF de l'imprimante PX-200 (texte + pictogrammes),
photo client img_px200_01 et registre des garanties."""
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

DATA = Path(__file__).parent / "data"
(DATA / "images").mkdir(parents=True, exist_ok=True)
(DATA / "manuels").mkdir(parents=True, exist_ok=True)
FIG = DATA / "figures_sources"
FIG.mkdir(exist_ok=True)

NOIR, ORANGE = (20, 20, 20), (235, 120, 20)


def fond(taille=300):
    img = Image.new("RGB", (taille, taille), "white")
    return img, ImageDraw.Draw(img)


def picto_encre():
    img, d = fond()
    d.polygon([(150, 40), (90, 160), (210, 160)], fill=NOIR)
    d.ellipse([88, 110, 212, 234], fill=NOIR)
    d.ellipse([120, 150, 150, 180], fill="white")
    return img


def picto_bourrage():
    img, d = fond()
    d.rectangle([60, 70, 240, 230], outline=NOIR, width=12)
    for y in (110, 145):
        d.line([(85, y), (215, y)], fill=NOIR, width=8)
    pts = [(60 + i * 20, 255 + (18 if i % 2 else 0)) for i in range(10)]
    d.line(pts, fill=NOIR, width=12, joint="curve")
    d.ellipse([195, 20, 275, 100], fill=ORANGE)
    d.text((228, 38), "!", fill="white", font_size=48)
    return img


def picto_wifi():
    img, d = fond()
    for r in (120, 85, 50):
        d.arc([150 - r, 190 - r, 150 + r, 190 + r], 225, 315, fill=NOIR, width=16)
    d.ellipse([136, 176, 164, 204], fill=NOIR)
    d.line([(195, 200), (265, 270)], fill=NOIR, width=14)
    d.line([(265, 200), (195, 270)], fill=NOIR, width=14)
    return img


def picto_tete():
    img, d = fond()
    d.polygon([(150, 35), (35, 250), (265, 250)], outline=NOIR, width=14)
    d.rectangle([140, 100, 160, 190], fill=NOIR)
    d.ellipse([138, 205, 162, 229], fill=NOIR)
    return img


PICTOS = [
    ("picto_encre", picto_encre, "Figure 1 – Pictogramme « goutte d'encre » : niveau d'encre bas.",
     "Voyant orange fixe avec la goutte : une cartouche est presque vide. Voyant orange clignotant avec la goutte : "
     "cartouche vide ou non reconnue. Remplacer la cartouche (section 4)."),
    ("picto_bourrage", picto_bourrage, "Figure 2 – Pictogramme « feuille et vague » : bourrage papier.",
     "Voyant orange clignotant avec la feuille et la vague : un bourrage papier bloque l'impression. Éteindre "
     "l'imprimante, ouvrir le capot arrière, retirer la feuille coincée en la tirant doucement vers soi, puis "
     "refermer le capot et appuyer sur le bouton Reprise. Ne jamais utiliser d'objet pointu."),
    ("picto_wifi", picto_wifi, "Figure 3 – Pictogramme « Wi-Fi barré » : connexion sans fil perdue.",
     "Voyant bleu clignotant avec le Wi-Fi barré : l'imprimante n'est plus connectée au réseau. Maintenir le "
     "bouton Wi-Fi 5 secondes puis relancer l'assistant de connexion."),
    ("picto_tete", picto_tete, "Figure 4 – Pictogramme « triangle d'avertissement » : erreur tête d'impression.",
     "Voyant rouge clignotant avec le triangle : erreur de la tête d'impression. Lancer un nettoyage de la tête "
     "depuis le menu Maintenance. Si l'erreur persiste après deux nettoyages, contacter le SAV."),
]


def generer_manuel():
    chemin = DATA / "manuels" / "manuel_PX-200.pdf"
    c = canvas.Canvas(str(chemin), pagesize=A4)
    largeur, hauteur = A4

    def titre(texte, y):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2 * cm, y, texte)

    def paragraphe(texte, y, taille=11, marge=2 * cm, largeur_max=95):
        c.setFont("Helvetica", taille)
        mots, ligne = texte.split(), ""
        for mot in mots:
            if len(ligne) + len(mot) > largeur_max:
                c.drawString(marge, y, ligne)
                y -= 0.55 * cm
                ligne = ""
            ligne += mot + " "
        c.drawString(marge, y, ligne)
        return y - 0.8 * cm

    # Page 1 : présentation
    c.setFont("Helvetica-Bold", 26)
    c.drawString(2 * cm, hauteur - 4 * cm, "Imprimante PX-200")
    c.setFont("Helvetica", 14)
    c.drawString(2 * cm, hauteur - 5 * cm, "Manuel d'utilisation et de dépannage")
    y = hauteur - 7 * cm
    titre("1. Présentation", y)
    y = paragraphe("La PX-200 est une imprimante jet d'encre couleur avec connexion Wi-Fi et USB. Elle imprime "
                   "jusqu'à 20 pages par minute en noir et 15 pages par minute en couleur. Le panneau de commande "
                   "comporte un bouton Marche, un bouton Reprise, un bouton Wi-Fi et un écran de voyants.", y - 0.8 * cm)
    titre("2. Garantie", y)
    y = paragraphe("La PX-200 est garantie 24 mois à compter de la date d'achat figurant sur la facture. La "
                   "garantie couvre les pannes matérielles mais pas les cartouches ni les dommages causés par une "
                   "chute ou un liquide. Le numéro de série (format PX200-XXXX) se trouve sous le capot arrière.",
                   y - 0.8 * cm)
    c.showPage()

    # Page 2 et 3 : voyants et pictogrammes
    for page, groupe in enumerate((PICTOS[:2], PICTOS[2:])):
        y = hauteur - 2.5 * cm
        titre("3. Voyants et pictogrammes du panneau" + (" (suite)" if page else ""), y)
        y -= 1.2 * cm
        for nom, fabrique, legende, explication in groupe:
            img = fabrique()
            img.save(FIG / f"{nom}.png")
            c.drawImage(str(FIG / f"{nom}.png"), 2 * cm, y - 5 * cm, width=5 * cm, height=5 * cm)
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(2 * cm, y - 5.6 * cm, legende)
            paragraphe(explication, y - 0.6 * cm, taille=11, marge=7.8 * cm, largeur_max=55)
            y -= 7.5 * cm
        c.showPage()

    # Page 4 : entretien
    y = hauteur - 2.5 * cm
    titre("4. Remplacement des cartouches", y)
    y = paragraphe("Ouvrir le capot avant, attendre que le chariot s'arrête au centre, appuyer sur la cartouche "
                   "pour la libérer puis insérer la nouvelle cartouche jusqu'au déclic. Utiliser uniquement des "
                   "cartouches PX-C20 (noir) et PX-C21 (couleur).", y - 0.8 * cm)
    titre("5. Contacter le service après-vente", y)
    paragraphe("Avant de contacter le SAV, noter le numéro de série et la description du voyant affiché. "
               "Le SAV vérifie la garantie à partir du numéro de série.", y - 0.8 * cm)
    c.save()
    return chemin


def generer_photo_client():
    """Photo du panneau prise par le client : pictogramme de bourrage, éclairage orange, flou, rotation."""
    picto = picto_bourrage().resize((220, 220))
    photo = Image.new("RGB", (448, 448), (58, 60, 66))
    ecran = Image.new("RGB", (300, 300), (205, 210, 200))
    ecran.paste(picto, (40, 40))
    photo.paste(ecran, (74, 74))
    d = ImageDraw.Draw(photo)
    d.ellipse([360, 380, 390, 410], fill=ORANGE)          # voyant orange allumé
    photo = photo.rotate(-7, fillcolor=(58, 60, 66)).filter(ImageFilter.GaussianBlur(1.2))
    random.seed(1)
    pixels = photo.load()
    for _ in range(6000):
        x, y = random.randrange(448), random.randrange(448)
        r, g, b = pixels[x, y]
        bruit = random.randint(-25, 25)
        pixels[x, y] = tuple(max(0, min(255, v + bruit)) for v in (r, g, b))
    photo.save(DATA / "images" / "img_px200_01.png")


def generer_registre():
    registre = {
        "PX200-0042": {"modele": "PX-200", "client": "Client A", "date_achat": "2025-03-14", "duree_mois": 24},
        "PX200-0007": {"modele": "PX-200", "client": "Client B", "date_achat": "2023-06-02", "duree_mois": 24},
        "PX200-0315": {"modele": "PX-200", "client": "Client C", "date_achat": "2026-09-30", "duree_mois": 24},
    }
    (DATA / "registre_garanties.json").write_text(json.dumps(registre, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    print(generer_manuel())
    generer_photo_client()
    generer_registre()
    print("Données générées dans", DATA)
