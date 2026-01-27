import base64
import os
import random
import string

import streamlit as st
from openai import OpenAI

from captcha.image import ImageCaptcha


# -----------------------
# Config UI
# -----------------------
st.set_page_config(page_title="ReflexIA (v3) — Actividades", page_icon="✅", layout="centered")
st.title("ReflexIA (v3) — Evaluador de Actividades")
st.caption("Evalúa coherencia entre el nivel Bloom declarado y la actividad (texto o imagen).")

# -----------------------
# OpenAI key (Streamlit Secrets primero)
# -----------------------
def get_api_key() -> str | None:
    if "OPENAI_API_KEY" in st.secrets:
        return st.secrets["OPENAI_API_KEY"]
    return os.getenv("OPENAI_API_KEY")

api_key = get_api_key()
if not api_key:
    st.error(
        "Falta configurar OPENAI_API_KEY.\n\n"
        "En Streamlit Cloud: Settings → Secrets → agrega:\n"
        "OPENAI_API_KEY = \"tu_clave\""
    )
    st.stop()

client = OpenAI(api_key=api_key)

# -----------------------
# ReflexIA v3 (Bloom)
# -----------------------
REFLEXIA_V3 = r"""
Rol
Eres ReflexIA, revisor crítico pedagógico.
Tu tarea es evaluar actividades formativas contrastándolas únicamente con el nivel cognitivo declarado en el objetivo de aprendizaje.

No decides a qué nivel “debería” llegar la actividad.
No propongas un nivel diferente al que declara el docente.

Entrada esperada
1) Objetivo de aprendizaje
2) Actividad (texto / imagen legible / URL pública accesible sin login)

Regla crítica
Si ReflexIA no puede leer ni acceder a la actividad real, NO evalúes ni supongas nada.
Debes: indicar que no es evaluable, describir qué insumo falta, y detener la evaluación.

Regla adicional (declaración explícita del nivel Bloom)
Si el objetivo incluye una línea con el formato:
"Nivel Bloom declarado por el docente: <X>"
entonces <X> es el nivel oficial a usar en toda la evaluación, incluso si el verbo del objetivo es ambiguo o no coincide.
No infieras ni sugieras otros niveles.

Procedimiento
Paso 0 — Verificación de acceso: si no puedes leer el contenido, detén la evaluación.
Paso 1 — Nivel cognitivo declarado: usa el nivel Bloom declarado explícitamente si está presente. Si no, identifica el nivel cognitivo explícito en el objetivo. No infieras intención.
Paso 2 — Proceso cognitivo activado: analiza qué proceso activa realmente la actividad observable.
Paso 3 — Evaluación de coherencia: emite un solo juicio: Coherente / Parcialmente coherente / No coherente.
Paso 4 — Fundamentación breve: máximo 3 puntos observables. Sin textos largos.
Paso 5 — Pregunta de mejora: no propongas otro nivel. Pregunta al docente cómo desea mejorar con alternativas.

Formato de salida
Si no evaluable:
Estado: No evaluable
Motivo: (frase directa)
Insumo requerido: (texto / captura específica)

Si evaluable:
1. Nivel cognitivo declarado en el objetivo:
2. Proceso cognitivo activado por la actividad:
3. Juicio de coherencia:
4. Fundamentación (máx. 3 puntos):
5. Pregunta de mejora al docente (con alternativas):

Estilo
Directo, preciso, sin ambigüedades, sin textos largos.
"""

# -----------------------
# Prompt de seguimiento (decisión del docente)
# -----------------------
REFLEXIA_FOLLOWUP = r"""
Eres ReflexIA. Vas a proponer un siguiente paso a partir de:
- Nivel Bloom declarado por el docente (NO lo cambies salvo que el docente lo pida explícitamente).
- Objetivo (texto) del docente
- Resultado previo de evaluación
- Decisión elegida por el docente

Reglas:
- No seas largo. Máximo 6 bullets.
- Da opciones accionables (consignas ejemplo, criterios, retroalimentación).
- Si el docente pide subir/bajar nivel, entonces sí: propone cómo reestructurar la misma actividad para ese nuevo nivel.
"""

# -----------------------
# Helpers OpenAI
# -----------------------
def to_data_url(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    b64 = base64.b64encode(raw).decode("utf-8")
    mime = uploaded_file.type or "image/png"
    return f"data:{mime};base64,{b64}"

def run_reflexia_text(model: str, objetivo: str, actividad: str) -> str:
    resp = client.responses.create(
        model=model,
        instructions=REFLEXIA_V3,
        input=f"{objetivo}\n\nActividad (texto):\n{actividad}",
    )
    return resp.output_text

def run_reflexia_image(model: str, objetivo: str, image_data_url: str) -> str:
    resp = client.responses.create(
        model=model,
        instructions=REFLEXIA_V3,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"{objetivo}\n\nActividad: (imagen adjunta)"},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    )
    return resp.output_text

# -----------------------
# CAPTCHA (anti-bots) — 100% Python, funciona en Streamlit Cloud
# -----------------------
def _new_captcha_text(n: int = 5) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))

def ensure_captcha():
    if "captcha_text" not in st.session_state:
        st.session_state["captcha_text"] = _new_captcha_text()
    if "captcha_ok" not in st.session_state:
        st.session_state["captcha_ok"] = False

def refresh_captcha():
    st.session_state["captcha_text"] = _new_captcha_text()
    st.session_state["captcha_ok"] = False
    st.session_state["captcha_input"] = ""

def captcha_block() -> bool:
    """
    Retorna True si está verificado. Si no, muestra UI y retorna False.
    """
    ensure_captcha()

    st.markdown("### Anti-bots (CAPTCHA)")
    st.caption("Escribe el código de la imagen para poder evaluar. (Puedes regenerarlo).")

    img = ImageCaptcha(width=220, height=80)
    png_bytes = img.generate(st.session_state["captcha_text"]).read()

    c1, c2 = st.columns([1, 1])
    with c1:
        st.image(png_bytes)
        st.button("Regenerar", on_click=refresh_captcha)
    with c2:
        user_in = st.text_input("Código CAPTCHA", key="captcha_input")
        if st.button("Verificar CAPTCHA"):
            if (user_in or "").strip().upper() == st.session_state["captcha_text"]:
                st.session_state["captcha_ok"] = True
                st.success("CAPTCHA verificado.")
            else:
                st.session_state["captcha_ok"] = False
                st.error("CAPTCHA incorrecto. Intenta de nuevo o regenera.")

    return bool(st.session_state.get("captcha_ok"))

st.divider()

# -----------------------
# Form
# -----------------------
modo = st.radio("Entrada de actividad", ["Texto", "Imagen"], horizontal=True)

with st.form("reflexia_form"):
    col1, col2 = st.columns([1, 1])

    with col1:
        bloom = st.selectbox(
            "Nivel Bloom (obligatorio)",
            ["Recordar", "Comprender", "Aplicar", "Analizar", "Evaluar", "Crear"],
            index=2,
        )

    with col2:
        # Fijo para evitar confusión (puedes reactivar selector luego si quieres)
        model = "gpt-4o-mini"
        st.text_input("Modelo", value=model, disabled=True)

    objetivo_texto = st.text_area(
        "Objetivo de aprendizaje (texto)",
        placeholder="Ej.: Usar el pasado simple para describir acciones de la semana pasada.",
        height=90,
    )

    if modo == "Texto":
        actividad_texto = st.text_area(
            "Actividad (texto)",
            placeholder="Pega la consigna y describe qué hace el estudiante.",
            height=160,
        )
        imagen = None
    else:
        imagen = st.file_uploader("Actividad (imagen)", type=["png", "jpg", "jpeg"])
        actividad_texto = None

    submit = st.form_submit_button("Evaluar")

if submit:
    if not objetivo_texto.strip():
        st.error("Falta el objetivo (texto).")
        st.stop()
    refresh_captcha()  # <-- AÑADE ESTA LÍNEA
    # CAPTCHA antes de consumir OpenAI
    if not captcha_block():
        st.stop()

    objetivo = f"Nivel Bloom declarado por el docente: {bloom}\nObjetivo de aprendizaje (texto): {objetivo_texto.strip()}"

    with st.spinner("Evaluando con ReflexIA…"):
        try:
            if modo == "Texto":
                if not actividad_texto or not actividad_texto.strip():
                    st.error("Falta la actividad en texto.")
                    st.stop()
                out = run_reflexia_text(model, objetivo, actividad_texto.strip())
            else:
                if not imagen:
                    st.error("No subiste ninguna imagen.")
                    st.stop()
                out = run_reflexia_image(model, objetivo, to_data_url(imagen))

            st.subheader("Resultado")
            st.code(out, language="text")

            # Guardar contexto para decisiones posteriores
            st.session_state["reflexia_ready"] = True
            st.session_state["reflexia_result"] = out
            st.session_state["reflexia_objetivo"] = objetivo
            st.session_state["reflexia_bloom"] = bloom
            st.session_state["reflexia_modo"] = modo
            st.session_state["reflexia_model"] = model

        except Exception as e:
            st.error(f"Error al llamar a la API: {e}")
            st.stop()

# -----------------------
# Decisión del docente (UI)
# -----------------------
if st.session_state.get("reflexia_ready"):
    st.subheader("Decisión del docente")

    decision = st.selectbox(
        "¿Qué quieres hacer ahora?",
        [
            "Elegir 2 mejoras concretas manteniendo el nivel",
            "Pedir 3 alternativas lúdicas manteniendo el nivel",
            "Crear una rúbrica breve (3 criterios)",
            "Redactar retroalimentación automática (1–2 líneas)",
            "Subir el nivel (decisión del docente)",
            "Bajar el nivel (decisión del docente)",
        ],
        index=0,
    )

    nuevo_nivel = None
    if "Subir el nivel" in decision or "Bajar el nivel" in decision:
        nuevo_nivel = st.selectbox(
            "Nuevo nivel Bloom (decisión del docente):",
            ["Recordar", "Comprender", "Aplicar", "Analizar", "Evaluar", "Crear"],
            index=["Recordar", "Comprender", "Aplicar", "Analizar", "Evaluar", "Crear"].index(
                st.session_state["reflexia_bloom"]
            ),
        )

    if st.button("Aplicar decisión"):
        if st.button("Aplicar decisión"):
        # CAPTCHA también para el follow-up (evita abuso)
        if not captcha_block():
            st.stop()

        follow_input = f"""
Nivel Bloom declarado por el docente: {st.session_state["reflexia_bloom"]}

Objetivo de aprendizaje (texto):
{st.session_state["reflexia_objetivo"].split('Objetivo de aprendizaje (texto):',1)[-1].strip()}

Resultado previo de ReflexIA:
{st.session_state["reflexia_result"]}

Decisión del docente:
{decision}
"""
        if nuevo_nivel:
            follow_input += f"\nNuevo nivel Bloom decidido por el docente: {nuevo_nivel}\n"

        with st.spinner("Generando siguiente paso…"):
            try:
                resp2 = client.responses.create(
                    model=st.session_state["reflexia_model"],
                    instructions=REFLEXIA_FOLLOWUP,
                    input=follow_input,
                )
                st.subheader("Siguiente paso sugerido")
                st.code(resp2.output_text, language="text")
            except Exception as e:
                st.error(f"Error al generar el siguiente paso: {e}")

st.divider()
st.caption("Implementación con Responses API (recomendada para proyectos nuevos).")

