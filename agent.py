import anthropic
import base64
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
GUIDELINES_DIR = BASE_DIR / "_guidelines"

client = anthropic.Anthropic()


def _load_guidelines() -> str:
    files = ["aggrator-stil.md", "tone-of-voice.md", "mal-artikkel.md"]
    parts = []
    for f in files:
        p = GUIDELINES_DIR / f
        if p.exists():
            parts.append(f"### {f}\n\n{p.read_text()}")
    return "\n\n---\n\n".join(parts)


GUIDELINES = _load_guidelines()


def _process_files(files_data: list) -> tuple[list, str]:
    """Returns (pdf_document_blocks, extracted_text) for uploaded files."""
    doc_blocks = []
    text_parts = []

    for f in files_data:
        name = f["name"]
        fbytes = f["bytes"]

        if name.lower().endswith(".pdf"):
            doc_blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(fbytes).decode("utf-8"),
                },
                "title": name,
            })
        elif name.lower().endswith(".docx"):
            try:
                from docx import Document
                doc = Document(BytesIO(fbytes))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                text_parts.append(f"[{name}]\n{text}")
            except Exception:
                pass
        elif name.lower().endswith(".pptx"):
            try:
                from pptx import Presentation
                prs = Presentation(BytesIO(fbytes))
                slides = []
                for i, slide in enumerate(prs.slides):
                    lines = [
                        shape.text.strip()
                        for shape in slide.shapes
                        if hasattr(shape, "text") and shape.text.strip()
                    ]
                    if lines:
                        slides.append(f"[Slide {i + 1}]\n" + "\n".join(lines))
                text_parts.append(f"[{name}]\n" + "\n\n".join(slides))
            except Exception:
                pass
        elif name.lower().endswith(".txt"):
            text_parts.append(f"[{name}]\n{fbytes.decode('utf-8', errors='replace')}")

    return doc_blocks, "\n\n".join(text_parts)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


def generate_questions(
    bullet_points: str,
    is_incubator: bool,
    company_name: str,
    files_data: Optional[list] = None,
) -> dict:
    doc_blocks, files_text = _process_files(files_data or [])

    context_text = f"Kulepunkter:\n{bullet_points}"
    if files_text:
        context_text += f"\n\nFiler fra selskapet:\n{files_text}"
    if is_incubator and company_name:
        context_text += f"\n\nInkubatorselskap: {company_name}"

    content = doc_blocks + [{"type": "text", "text": context_text}]

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="""Du er redaksjonsassistent for Aggrator. Analyser kulepunktene og bestem:
1. Hvilken artikkeltype som passer best:
   - A = Nyhetsmelding (kunngjøringer, tilskudd, samarbeidsavtaler, 200–350 ord)
   - B = Ny-partner (selskap inn i Aggrator, 300–450 ord)
   - C = Program/rapport (arrangement, turer, 500–800 ord)
   - D = Analytisk listicle (trender, gründeranalyse, 600–1000 ord)
2. Hvilke konkrete opplysninger som mangler for å skrive artikkelen ferdig

Returner kun JSON på dette formatet:
{"article_type": "A", "type_reasoning": "kort begrunnelse", "questions": ["spørsmål 1", "spørsmål 2"]}

Regler:
- Maks 6 spørsmål
- Spør kun om det som faktisk mangler – ikke om ting som allerede er oppgitt i kulepunkter eller filer
- Norsk bokmål""",
        messages=[{"role": "user", "content": content}],
    )

    data = _extract_json(resp.content[0].text)
    return {
        "article_type": data.get("article_type", "A"),
        "type_reasoning": data.get("type_reasoning", ""),
        "questions": data.get("questions", []),
    }


NEWS_TYPE_LABELS = {
    "type_a": "Type A – Nyhetsmelding",
    "type_b": "Type B – Ny-partner",
    "type_c": "Type C – Program/arrangement-rapport",
    "type_d": "Type D – Analytisk artikkel",
    "annet":  "Annet",
}


def _build_context(news_type: str, fields: dict) -> str:
    f = fields
    if news_type == "type_b":
        return (
            f"Selskapsnavn: {f['company_name']}\n"
            f"Gründer / daglig leder: {f['founder'] or '[MANGLER: navn]'}\n"
            f"Ansvarlig hos Aggrator (KAM): {f['responsible']}\n"
            f"Hva driver selskapet med: {f['description']}\n"
            f"Ekstra notater: {f['notes'] or '(ingen)'}"
        )
    elif news_type == "type_a":
        return (
            f"Hva handler nyheten om: {f['aggrator_what']}\n"
            f"Hvem er involvert: {f['aggrator_who'] or '(ikke oppgitt)'}\n"
            f"Ekstra notater: {f['notes'] or '(ingen)'}"
        )
    elif news_type == "type_c":
        return (
            f"Program / arrangement: {f['topic']}\n"
            f"Hva skjedde: {f['key_points']}\n"
            f"Ekstra notater: {f['notes'] or '(ingen)'}"
        )
    elif news_type == "type_d":
        return (
            f"Tema: {f['topic']}\n"
            f"Nøkkelpunkter: {f['key_points']}\n"
            f"Ekstra notater: {f['notes'] or '(ingen)'}"
        )
    elif news_type == "annet":
        return f"Beskrivelse: {f['notes']}"
    return ""


def generate_article(
    news_type: str,
    fields: dict,
    corrections: dict,
    files_data: Optional[list] = None,
) -> str:
    doc_blocks, files_text = _process_files(files_data or [])

    lessons_block = ""
    lessons = corrections.get("lessons", [])[-6:]
    if lessons:
        lessons_block = "\n\n## Lærte stilregler fra tidligere korrigeringer:\n"
        for lesson in lessons:
            lessons_block += f"- {lesson['lesson']}\n"

    system = f"""Du er redaksjonsassistent for Aggrator. Skriv en ferdig artikkel på norsk bokmål.

## Retningslinjer:
{GUIDELINES}
{lessons_block}

REGLER:
- Aldri oppfinn fakta – bruk kun det som er oppgitt
- Manglende felt skrives som [MANGLER: beskrivelse]
- Skriv alltid "Vi i Aggrator" (aldri tredjeperson)
- Ingen reklamespråk: "revolusjonerende", "banebrytende", "game-changing" er forbudt
- Sitater i eget innrykk: – [sitat], sier [Navn], [Tittel] i [Selskap].
- Bildetekst i kursiv til slutt"""

    context = _build_context(news_type, fields)
    user_text = (
        f"Type nyhet: {NEWS_TYPE_LABELS.get(news_type, news_type)}\n\n"
        f"{context}"
    )
    if files_text:
        user_text += f"\n\nFILER FRA SELSKAPET:\n{files_text}"

    content = doc_blocks + [{"type": "text", "text": user_text}]

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return resp.content[0].text.strip()


def extract_lesson(before: str, after: str, corrections_file: Path) -> None:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system="Du er redaksjonsassistent for Aggrator. Identifiser den viktigste stilregelen som kan læres av denne korrigeringen. Svar med én konkret, handlingsbar regel på norsk bokmål. Ingen forklaring – bare regelen.",
        messages=[{
            "role": "user",
            "content": f"FØR korrektur:\n{before[:1500]}\n\nETTER korrektur:\n{after[:1500]}\n\nHvilken stilregel representerer denne endringen?",
        }],
    )
    lesson = resp.content[0].text.strip()

    data = json.loads(corrections_file.read_text()) if corrections_file.exists() else {"corrections": [], "lessons": []}
    data.setdefault("lessons", []).append({
        "lesson": lesson,
        "ts": datetime.now().isoformat(),
    })
    data["lessons"] = data["lessons"][-20:]
    corrections_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def update_company_profile(
    company_name: str,
    before: str,
    after: str,
    saker_dir: Path,
) -> None:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system="""Identifiser faktaopplysninger om selskapet som ble korrigert (navn, produktnavn, titler, tall, datoer osv.).
Returner JSON: {"corrections": [{"field": "beskrivelse av felt", "old": "gammel verdi", "new": "ny verdi"}]}
Hvis ingen faktakorrigeringer: {"corrections": []}""",
        messages=[{
            "role": "user",
            "content": f"FØR selskapsgjennomlesning:\n{before[:1500]}\n\nETTER selskapsgjennomlesning:\n{after[:1500]}",
        }],
    )

    data = _extract_json(resp.content[0].text)
    corrections = data.get("corrections", [])
    if not corrections:
        return

    slug = (
        company_name.lower()
        .replace(" ", "-")
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
    )

    company_dir = saker_dir / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "kontekst").mkdir(exist_ok=True)
    (company_dir / "output").mkdir(exist_ok=True)

    corrections_text = "\n".join(
        f"- **{c['field']}**: ~~{c['old']}~~ → {c['new']}" for c in corrections
    )
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    update_block = f"\n\n## Faktakorrigeringer fra selskap ({timestamp})\n\n{corrections_text}\n"

    claude_md = company_dir / "CLAUDE.md"
    if claude_md.exists():
        claude_md.write_text(claude_md.read_text() + update_block)
    else:
        claude_md.write_text(f"# {company_name}\n{update_block}")
