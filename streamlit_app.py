import streamlit as st
import tempfile
import os
import sys
import io
import zipfile

st.set_page_config(
    page_title="Automatyzator Rozliczeń Medycznych",
    layout="wide"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WZORCOWE_DIR = os.path.join(BASE_DIR, "pliki_wzorcowe")
CENNIK_DIR = os.path.join(BASE_DIR, "Cennik")

st.title("Automatyzator Rozliczeń Medycznych")

if not os.path.isdir(WZORCOWE_DIR) or not os.path.isdir(CENNIK_DIR):
    st.error("Brakuje folderów pliki_wzorcowe lub Cennik w katalogu aplikacji.")
    st.stop()

st.subheader("Wgraj plik z danymi jednostek")
uploaded_file = st.file_uploader("Plik Excel z danymi (Jednostki)", type=["xlsx", "xls"])

col1, col2 = st.columns(2)
run_full = col1.button("Uruchom pełny proces", type="primary", disabled=uploaded_file is None)
run_unmatched = col2.button("Tylko braki wzorca", disabled=uploaded_file is None)

if run_full or run_unmatched:
    import backend

    with tempfile.TemporaryDirectory() as tmp_dir:
        jednostki_dir = os.path.join(tmp_dir, "Jednostki")
        sprawdzone_dir = os.path.join(tmp_dir, "pliki_sprawdzone")
        wynik_dir = os.path.join(tmp_dir, "Wynik")
        os.makedirs(jednostki_dir)

        input_path = os.path.join(jednostki_dir, uploaded_file.name)
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        log_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = log_capture

        try:
            with st.spinner("Przetwarzanie..."):
                if run_full:
                    backend.main(jednostki_dir, WZORCOWE_DIR, CENNIK_DIR, wynik_dir, sprawdzone_dir)
                else:
                    backend.run_unmatched_only(jednostki_dir, WZORCOWE_DIR, sprawdzone_dir)
        except Exception as e:
            print(f"BŁĄD KRYTYCZNY: {e}")
        finally:
            sys.stdout = old_stdout

        logs = log_capture.getvalue()

        st.subheader("Logi procesu")
        st.text_area("", value=logs, height=400, disabled=True)

        result_dir = wynik_dir if run_full else sprawdzone_dir
        zip_name = "Wynik.zip" if run_full else "pliki_sprawdzone.zip"

        if os.path.isdir(result_dir) and os.listdir(result_dir):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(result_dir):
                    fpath = os.path.join(result_dir, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, fname)
            zip_buffer.seek(0)

            st.success("Przetwarzanie zakończone!")
            st.download_button(
                label=f"Pobierz wyniki — {zip_name}",
                data=zip_buffer,
                file_name=zip_name,
                mime="application/zip",
                type="primary"
            )
        else:
            st.warning("Nie wygenerowano plików wynikowych.")
