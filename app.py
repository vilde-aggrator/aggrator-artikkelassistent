import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

import agent

# --- Paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SAKER_DIR = BASE_DIR / "saker"
DATA_DIR.mkdir(exist_ok=True)
CORRECTIONS_FILE = DATA_DIR / "corrections.json"

# --- Page config ---
st.set_page_config(page_title="Aggrator – Artikkelassistent", layout="centered")

st.markdown("""
<style>
    .stApp { max-width: 780px; margin: 0 auto; }
    h1 { color: #1b4332; }
    .step-done { color: #40916c; font-size: 12px; text-align: center; }
    .step-active { color: #1b4332; font-weight: bold; font-size: 13px; text-align: center; }
    .step-inactive { color: #aaa; font-size: 12px; text-align: center; }
    .step-disabled { color: #ddd; font-size: 12px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- News type definitions ---
NEWS_TYPES = {
    "type_b": "Ny-partner (selskap inn i Aggrator)",
    "type_a": "Nyhetsmelding (kunngjøring, tilskudd, samarbeidsavtale)",
    "type_c": "Program / arrangement-rapport",
    "type_d": "Analytisk artikkel (trender, bransje, ressurs, politikk)",
    "annet":  "Annet",
}

# --- State init ---
DEFAULTS = {
    "stage": "input",
    "news_type": "",
    "responsible": "",
    "uploaded_files": [],
    "draft": "",
    "vilde_edit": "",
    "company_edit": "",
    # Selskapsnyhet
    "company_name": "",
    "kam": "",
    "main_contact": "",
    "other_team": "",
    "description": "",
    # Aggrator-nyhet
    "aggrator_what": "",
    "aggrator_who": "",
    # Bransje / Ressurs
    "topic": "",
    "key_points": "",
    # Politikk
    "policy_what": "",
    "policy_relevance": "",
    # Felles
    "notes": "",
    # Bilde til artikkelen
    "article_image": None,
    # Spørsmålsrunde
    "questions": [],
    "fields_snapshot": {},
    "answers_snapshot": {},
    "pending_generation": None,
    "email_sent": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# news_type er knyttet til artikkeltype-velgeren, som bare rendres i input-stadiet.
# Streamlit sletter widget-state for ikke-renderte widgets, så uten dette ville
# news_type bli tom på senere stadier – og _build_context ville da droppe alle felt.
# Re-hydrer derfor fra snapshot i alle stadier etter input.
if st.session_state.stage != "input":
    _snap_type = st.session_state.fields_snapshot.get("news_type")
    if _snap_type:
        st.session_state.news_type = _snap_type

# --- API key check ---
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("**ANTHROPIC_API_KEY mangler.** Start appen med: `ANTHROPIC_API_KEY=sk-... streamlit run app.py`")
    st.stop()

# --- Helpers ---
def load_corrections() -> dict:
    if CORRECTIONS_FILE.exists():
        return json.loads(CORRECTIONS_FILE.read_text())
    return {"corrections": [], "lessons": []}

def save_correction(source: str, before: str, after: str) -> None:
    data = load_corrections()
    data.setdefault("corrections", []).append({
        "source": source,
        "before": before[:3000],
        "after": after[:3000],
        "ts": datetime.now().isoformat(),
    })
    data["corrections"] = data["corrections"][-20:]
    CORRECTIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def reset_session() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]

def is_incubator_article() -> bool:
    return st.session_state.news_type == "type_b"

def show_article_image(width: int = 420) -> None:
    img = st.session_state.get("article_image")
    if img and img.get("bytes"):
        st.image(img["bytes"], caption=img.get("name", ""), width=width)

# --- Progress bar ---
STAGE_ORDER = ["input", "draft", "vilde_review", "company_review", "done"]
STAGE_LABELS = ["Inndata", "Utkast", "Vilde", "Selskap", "Ferdig"]

def show_progress() -> None:
    current_idx = STAGE_ORDER.index(st.session_state.stage) if st.session_state.stage in STAGE_ORDER else 0
    cols = st.columns(len(STAGE_LABELS))
    for i, (col, label) in enumerate(zip(cols, STAGE_LABELS)):
        if i == 3 and not is_incubator_article():
            col.markdown(f"<p class='step-disabled'>{label}</p>", unsafe_allow_html=True)
        elif i < current_idx:
            col.markdown(f"<p class='step-done'>✓ {label}</p>", unsafe_allow_html=True)
        elif i == current_idx:
            col.markdown(f"<p class='step-active'>{label}</p>", unsafe_allow_html=True)
        else:
            col.markdown(f"<p class='step-inactive'>{label}</p>", unsafe_allow_html=True)
    st.divider()

show_progress()


# ─── STAGE: input ─────────────────────────────────────────────────────────────

if st.session_state.stage == "input":
    st.title("Ny artikkel")

    st.selectbox(
        "Hva slags nyhet er dette?",
        options=[""] + list(NEWS_TYPES.keys()),
        format_func=lambda k: "Velg type ..." if k == "" else NEWS_TYPES[k],
        key="news_type",
    )

    news = st.session_state.news_type
    ready = False

    if news == "type_b":
        st.divider()
        st.text_input("Selskapsnavn *", key="company_name")
        st.text_input(
            "Selskapets hovedkontakt – fullt navn og rolle *",
            key="main_contact",
            placeholder="F.eks. Richard Nystad, daglig leder",
            help="Personen Aggrator har som hovedkontakt i selskapet – som regel daglig leder eller gründer. Brukes til sitat og omtale i artikkelen.",
        )
        st.text_input(
            "Andre grunnleggere / sentrale teammedlemmer (valgfritt)",
            key="other_team",
            placeholder="F.eks. Kari Hansen, teknisk sjef / Per Olsen, medgründer – la stå tom hvis ingen andre",
            help="Kun hvis det er flere du vil ha med. La feltet stå tomt hvis det ikke er noen andre.",
        )
        st.text_area("Hva driver selskapet med? *", key="description", height=100)
        st.text_area("Ekstra notater", key="notes", height=90,
            placeholder="Investeringsbeløp, partnere, milepæler, sitater, lenker ...")
        ready = bool(
            st.session_state.company_name.strip()
            and st.session_state.main_contact.strip()
            and st.session_state.description.strip()
        )

    elif news == "type_a":
        st.divider()
        st.text_area("Hva handler nyheten om? *", key="aggrator_what", height=110,
            placeholder="Ny ansatt, tilskudd, samarbeidsavtale, milepæl ...")
        st.text_input("Hvem er involvert? (navn og rolle)", key="aggrator_who")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.aggrator_what.strip())

    elif news == "type_c":
        st.divider()
        st.text_input("Program / arrangement *", key="topic",
            placeholder="F.eks. AgriScale Spain 2026, Esse kull 3 ...")
        st.text_area("Beskriv arrangementet *", key="key_points", height=150,
            placeholder="Fortell fritt – bakgrunn, høydepunkter, møter, resultater, stemning, deltakere, sitater ... Skriv det du husker, agenten finner strukturen.")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.topic.strip() and st.session_state.key_points.strip())

    elif news == "type_d":
        st.divider()
        st.text_input("Tema / tittel *", key="topic",
            placeholder="F.eks. «Fem trender som former landbruket nå» ...")
        st.text_area("Nøkkelpunkter *", key="key_points", height=130,
            placeholder="Trender, argumenter, eksempler, kilder ...")
        st.text_area("Ekstra notater", key="notes", height=90)
        ready = bool(st.session_state.topic.strip() and st.session_state.key_points.strip())

    elif news == "annet":
        st.divider()
        st.text_area("Beskriv hva artikkelen handler om *", key="notes", height=160,
            placeholder="Skriv fritt – jo mer kontekst du gir, jo bedre blir artikkelen ...")
        ready = bool(st.session_state.notes.strip())

    if news:
        st.divider()
        file_label = (
            "Filer fra selskapet (pitch deck, pressemelding ...)"
            if news == "type_b"
            else "Kontekstfiler (rapport, pressemelding, bakgrunnsnotat ...)"
        )
        with st.expander("Legg ved kildefiler (valgfritt)"):
            uploaded = st.file_uploader(
                file_label,
                type=["pdf", "pptx", "docx", "txt"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )

        st.markdown("**Bilde til artikkelen \\***")
        image_file = st.file_uploader(
            "Bilde til artikkelen",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
            label_visibility="collapsed",
            key="image_uploader",
        )
        if image_file is not None:
            st.image(image_file, width=320)
        elif st.session_state.article_image:
            st.caption(f"Tidligere opplastet: {st.session_state.article_image['name']}")

        responsible_label = (
            "Ansvarlig for selskapet hos Aggrator (KAM) *"
            if news == "type_b"
            else "Ditt navn *"
        )
        st.text_input(responsible_label, key="responsible")

        has_image = image_file is not None or bool(st.session_state.article_image)

        st.divider()
        if not has_image:
            st.caption("Du må laste opp et bilde for å generere artikkelen.")
        if st.button("Generer artikkel →", type="primary",
                     disabled=not (ready and st.session_state.responsible.strip() and has_image)):
            st.session_state.uploaded_files = [
                {"name": f.name, "bytes": f.read()} for f in (uploaded or [])
            ]
            if image_file is not None:
                st.session_state.article_image = {
                    "name": image_file.name,
                    "bytes": image_file.getvalue(),
                    "mime": image_file.type or "image/jpeg",
                }
            fields = {
                "company_name":  st.session_state.company_name,
                "main_contact":  st.session_state.main_contact,
                "other_team":    st.session_state.other_team,
                "description":   st.session_state.description,
                "aggrator_what": st.session_state.aggrator_what,
                "aggrator_who":  st.session_state.aggrator_who,
                "topic":         st.session_state.topic,
                "key_points":    st.session_state.key_points,
                "notes":         st.session_state.notes,
                "responsible":   st.session_state.responsible,
            }
            # news_type lagres slik at type-velgeren gjenopprettes ved "← Tilbake"
            # (Streamlit sletter widget-state for ikke-renderte widgets)
            st.session_state.fields_snapshot = {**fields, "news_type": news}

            with st.spinner("Analyserer informasjon..."):
                context = agent._build_context(news, fields)
                q_result = agent.generate_questions(
                    context=context,
                    is_incubator=(news == "type_b"),
                    company_name=st.session_state.company_name,
                    news_type=news,
                    files_data=st.session_state.uploaded_files,
                )

            questions = q_result.get("questions", [])
            if questions:
                st.session_state.questions = questions
                st.session_state.stage = "questions"
                st.rerun()
            else:
                # Selve skrivingen skjer streamende i draft-stadiet
                st.session_state.pending_generation = {"news_type": news, "fields": fields}
                st.session_state.pop("draft_textarea", None)
                st.session_state.stage = "draft"
                st.rerun()


# ─── STAGE: questions ─────────────────────────────────────────────────────────

elif st.session_state.stage == "questions":
    st.title("Utfyllende spørsmål")
    st.caption("Agenten trenger litt mer informasjon for å skrive et godt utkast. Du kan hoppe over spørsmål du ikke har svar på nå.")

    for i, q in enumerate(st.session_state.questions):
        # Gjenopprett tidligere svar når man kommer tilbake fra utkast
        # (Streamlit sletter widget-state for ikke-renderte widgets)
        if f"q_answer_{i}" not in st.session_state and i in st.session_state.answers_snapshot:
            st.session_state[f"q_answer_{i}"] = st.session_state.answers_snapshot[i]
        st.text_area(q, key=f"q_answer_{i}", height=80)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            for k, v in st.session_state.fields_snapshot.items():
                st.session_state[k] = v
            st.session_state.stage = "input"
            st.rerun()
    with col2:
        if st.button("Generer utkast →", type="primary"):
            answers = []
            answers_snap = {}
            for i, q in enumerate(st.session_state.questions):
                ans = st.session_state.get(f"q_answer_{i}", "").strip()
                answers_snap[i] = ans
                if ans:
                    answers.append(f"- {q}: {ans}")
            st.session_state.answers_snapshot = answers_snap

            fields = dict(st.session_state.fields_snapshot)
            if answers:
                fields["extra_context"] = "\n".join(answers)

            # Selve skrivingen skjer streamende i draft-stadiet
            st.session_state.pending_generation = {
                "news_type": st.session_state.news_type,
                "fields": fields,
            }
            st.session_state.pop("draft_textarea", None)
            st.session_state.stage = "draft"
            st.rerun()


# ─── STAGE: draft ─────────────────────────────────────────────────────────────

elif st.session_state.stage == "draft":
    st.title("Artikkelutkast")

    # Streamende generering: skriv artikkelen synlig bit for bit, lagre, og
    # rerun til den redigerbare visningen.
    if st.session_state.pending_generation:
        pg = st.session_state.pending_generation
        st.caption("Skriver artikkelen …")
        show_article_image()
        try:
            stream = agent.generate_article_stream(
                news_type=pg["news_type"],
                fields=pg["fields"],
                corrections=load_corrections(),
                files_data=st.session_state.uploaded_files,
                image_data=st.session_state.article_image,
            )
            draft = st.write_stream(stream).strip()
        except Exception:
            # Faller tilbake til vanlig (ikke-streamende) generering ved feil
            draft = agent.generate_article(
                news_type=pg["news_type"],
                fields=pg["fields"],
                corrections=load_corrections(),
                files_data=st.session_state.uploaded_files,
                image_data=st.session_state.article_image,
            )
        st.session_state.draft = draft
        st.session_state.vilde_edit = draft
        st.session_state.pop("draft_textarea", None)
        st.session_state.pending_generation = None
        st.rerun()

    st.caption("Rediger fritt og fyll inn eventuelle [MANGLER]-felt før du sender til korrektur.")

    if "draft_textarea" not in st.session_state:
        st.session_state["draft_textarea"] = st.session_state.draft

    tab1, tab2 = st.tabs(["Rediger", "Forhåndsvisning"])
    with tab1:
        st.text_area("Artikkel", key="draft_textarea", height=520, label_visibility="collapsed")
    with tab2:
        st.markdown(st.session_state.get("draft_textarea", st.session_state.draft))
        show_article_image()

    current = st.session_state.get("draft_textarea", st.session_state.draft)
    if "[MANGLER" in current:
        st.warning("Utkastet inneholder fortsatt [MANGLER]-felt. Du kan fylle dem inn nå, eller la Vilde gjøre det i korrektur.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            # Ett steg tilbake: til spørsmålene hvis de finnes, ellers til inndata
            st.session_state.pop("draft_textarea", None)
            if st.session_state.questions:
                st.session_state.stage = "questions"
            else:
                for k, v in st.session_state.fields_snapshot.items():
                    st.session_state[k] = v
                st.session_state.stage = "input"
            st.rerun()
    with col2:
        if st.button("Send til korrektur hos Vilde →", type="primary"):
            edited = st.session_state.get("draft_textarea", st.session_state.draft)
            st.session_state.draft = edited
            st.session_state.vilde_edit = edited
            sent, msg = agent.send_article_to_vilde(
                article=edited,
                responsible=st.session_state.responsible,
                news_type=st.session_state.news_type,
                image_data=st.session_state.article_image,
            )
            st.session_state.email_sent = (sent, msg)
            if "vilde_textarea" in st.session_state:
                del st.session_state["vilde_textarea"]
            st.session_state.stage = "vilde_review"
            st.rerun()


# ─── STAGE: vilde_review ──────────────────────────────────────────────────────

elif st.session_state.stage == "vilde_review":
    st.title("Korrektur – kommunikasjonssjef")
    st.caption("Les artikkelen og gjør endringer direkte i tekstfeltet.")

    if st.session_state.email_sent is not None:
        sent, msg = st.session_state.email_sent
        if sent:
            st.success(msg)
        elif "ikke konfigurert" in msg:
            st.warning(
                f"{msg}. "
                "For å aktivere e-postvarsler, fyll ut SMTP_HOST, SMTP_USER og "
                "SMTP_PASSWORD i `nyhetssaker/interface/.env` og start appen på nytt."
            )
        else:
            st.warning(
                f"{msg}. Artikkelen er ikke påvirket – du kan fortsette korrekturen, "
                "og eventuelt prøve å sende på nytt fra utkast-steget."
            )
        st.session_state.email_sent = None

    if "vilde_textarea" not in st.session_state:
        st.session_state["vilde_textarea"] = st.session_state.vilde_edit

    tab1, tab2 = st.tabs(["Rediger", "Forhåndsvisning"])
    with tab1:
        st.text_area("Artikkel", key="vilde_textarea", height=520, label_visibility="collapsed")
    with tab2:
        st.markdown(st.session_state.get("vilde_textarea", st.session_state.vilde_edit))
        show_article_image()

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            st.session_state.stage = "draft"
            st.rerun()
    with col2:
        if st.button("Godkjenn →", type="primary"):
            edited = st.session_state.get("vilde_textarea", st.session_state.vilde_edit)
            st.session_state.vilde_edit = edited
            st.session_state.company_edit = edited

            if edited.strip() != st.session_state.draft.strip():
                save_correction("vilde", st.session_state.draft, edited)
                with st.spinner("Lagrer stilkorrigeringer..."):
                    agent.extract_lesson(st.session_state.draft, edited, CORRECTIONS_FILE)

            if is_incubator_article() and st.session_state.company_name.strip():
                if "company_textarea" in st.session_state:
                    del st.session_state["company_textarea"]
                st.session_state.stage = "company_review"
            else:
                st.session_state.stage = "done"
            st.rerun()


# ─── STAGE: company_review ────────────────────────────────────────────────────

elif st.session_state.stage == "company_review":
    company = st.session_state.company_name or "Selskapet"
    st.title(f"Korrektur – {company}")
    st.caption("Gjør korrigeringer på vegne av selskapet.")

    if "company_textarea" not in st.session_state:
        st.session_state["company_textarea"] = st.session_state.company_edit

    tab1, tab2 = st.tabs(["Rediger", "Forhåndsvisning"])
    with tab1:
        st.text_area("Artikkel", key="company_textarea", height=520, label_visibility="collapsed")
    with tab2:
        st.markdown(st.session_state.get("company_textarea", st.session_state.company_edit))
        show_article_image()

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Tilbake"):
            st.session_state.stage = "vilde_review"
            st.rerun()
    with col2:
        if st.button("Godkjenn og avslutt →", type="primary"):
            edited = st.session_state.get("company_textarea", st.session_state.company_edit)
            st.session_state.company_edit = edited

            if edited.strip() != st.session_state.vilde_edit.strip():
                save_correction(company, st.session_state.vilde_edit, edited)
                with st.spinner(f"Oppdaterer profil for {company}..."):
                    agent.update_company_profile(
                        company,
                        st.session_state.vilde_edit,
                        edited,
                        SAKER_DIR,
                    )

            st.session_state.stage = "done"
            st.rerun()


# ─── STAGE: done ──────────────────────────────────────────────────────────────

elif st.session_state.stage == "done":
    st.success("Artikkelen er godkjent og klar for publisering!")

    final = (
        st.session_state.company_edit
        or st.session_state.vilde_edit
        or st.session_state.draft
    )

    corrections_data = load_corrections()
    lessons = corrections_data.get("lessons", [])
    if lessons:
        with st.expander(f"Agenten har lært {len(lessons)} stilregel(er) totalt"):
            for l in lessons[-10:]:
                st.markdown(f"- {l['lesson']} *({l.get('ts', '')[:10]})*")

    tab1, tab2 = st.tabs(["Forhåndsvisning", "Markdown"])
    with tab1:
        st.markdown(final)
        show_article_image()
    with tab2:
        st.code(final, language="markdown")

    st.divider()
    img = st.session_state.get("article_image")
    cols = st.columns(3 if img else 2)
    with cols[0]:
        st.download_button(
            "Last ned .md",
            data=final,
            file_name=f"artikkel-{datetime.now().strftime('%Y%m%d-%H%M')}.md",
            mime="text/markdown",
        )
    if img:
        with cols[1]:
            st.download_button(
                "Last ned bilde",
                data=img["bytes"],
                file_name=img.get("name", "bilde.jpg"),
                mime=img.get("mime", "image/jpeg"),
            )
    with cols[-1]:
        if st.button("Skriv ny artikkel", type="primary"):
            reset_session()
            st.rerun()
