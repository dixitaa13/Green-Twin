import streamlit as st

def main():
    st.set_page_config(page_title="GreenTwin Prototype", layout="wide")
    st.title("GreenTwin: Sustainable Logistics Prototype")
    st.markdown("""
    This is a minimal starter. Type **next** in the console to proceed to Step 2.
    """)
    st.write("Your environment is set up correctly!")

if __name__ == "__main__":
    main()
