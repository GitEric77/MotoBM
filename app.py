import streamlit as st
import subprocess
import os
import pandas as pd
from io import StringIO
import base64
import uuid
import hashlib
from datetime import datetime

st.set_page_config(page_title="MOTOTRBO Zone Generator", page_icon="📻", layout="wide")

# Function to generate a unique session ID for each user
def get_session_id():
    # Check if session_id exists in session state
    if 'session_id' not in st.session_state:
        # Generate a unique session ID based on timestamp and random UUID
        unique_id = f"{datetime.now().timestamp()}_{uuid.uuid4()}"
        # Hash the ID to make it shorter but still unique
        hashed_id = hashlib.md5(unique_id.encode()).hexdigest()
        # Store in session state
        st.session_state.session_id = hashed_id
    
    return st.session_state.session_id

# Get or create a unique session ID for the current user
session_id = get_session_id()

st.title("MOTOTRBO Zone Generator")
st.markdown("Generate MOTOTRBO zone files from BrandMeister repeater list")

# Create tabs for different modes
tab1, tab2 = st.tabs(["Standard Mode", "Talkgroup Mode"])

with tab1:
    st.header("Standard Mode")
    st.markdown("Create a single zone file with channels for each repeater timeslot")
    col1, col2 = st.columns(2)
    
    with col1:
        zone_name = st.text_input("Zone Name", help="Choose a name for your zone")
        band = st.selectbox("Band", ["vhf", "uhf"], help="Select repeater band")
        
        search_type = st.selectbox("Search Type", ["mcc", "qth", "gps"], 
                                  help="Select repeaters by MCC code, QTH locator index or GPS coordinates")
        
        if search_type == "mcc":
            mcc = st.text_input("MCC Code or Country Code", 
                               help="First repeater ID digits (usually 3 digits MCC) or two letter country code")
        
        elif search_type == "qth":
            qth = st.text_input("QTH Locator", help="QTH locator index like KO26BX")
            radius = st.number_input("Radius (km)", min_value=1, value=100, 
                                    help="Area radius in kilometers around the center of the chosen QTH locator")
            st.text(f"Equivalent: {radius:.1f} km = {radius * 0.621371:.1f} miles")
        
        elif search_type == "gps":
            col_lat, col_lon = st.columns(2)
            with col_lat:
                latitude = st.number_input("Latitude", format="%.6f")
            with col_lon:
                longitude = st.number_input("Longitude", format="%.6f")
            radius = st.number_input("Radius (km)", min_value=1, value=100, 
                                    help="Area radius in kilometers around the GPS coordinates")
            st.text(f"Equivalent: {radius:.1f} km = {radius * 0.621371:.1f} miles")
    
    with col2:
        force_download = st.checkbox("Force Download", 
                                    help="Forcibly download repeater list even if it exists locally")
        
        only_with_power = st.checkbox("Only with Power", 
                                     help="Only select repeaters with defined power")
        
        if only_with_power:
            min_power = st.number_input("Minimum Power (W)", min_value=1, value=10,
                                      help="Minimum power in watts")
        
        six_digit = st.checkbox("6-Digit ID Only", value=True,
                               help="Only select repeaters with 6 digit ID (real repeaters, not hotspots)")
        
        zone_capacity = st.number_input("Zone Capacity", min_value=1, value=160, 
                                       help="Channel capacity within zone. 160 by default for top models, use 16 for lite models")
        
        customize = st.checkbox("Include Custom Values", 
                               help="Include customized values for each channel")
        
        callsign_filter = st.text_input("Callsign Filter", 
                                       help="Only list callsigns containing specified string like a region number")
    
    if st.button("Generate Zone Files", key="generate_standard"):
        if search_type == "mcc" and not mcc:
            st.error("Please enter an MCC code or country code")
        elif search_type == "qth" and not qth:
            st.error("Please enter a QTH locator")
        elif search_type == "gps" and (latitude == 0 and longitude == 0):
            st.error("Please enter valid GPS coordinates")
        elif not zone_name:
            st.error("Please enter a zone name")
        else:
            # Build command with user-specific output directory
            user_output_dir = f"output_{session_id}"
            cmd = ["python", "zone.py", "-n", zone_name, "-b", band, "-t", search_type, "-o", user_output_dir]
            
            if force_download:
                cmd.extend(["-f"])
            
            if search_type == "mcc":
                cmd.extend(["-m", mcc])
            elif search_type == "qth":
                cmd.extend(["-q", qth, "-r", str(radius)])
            elif search_type == "gps":
                # Handle negative coordinates using the format from README example
                if latitude < 0:
                    cmd.extend([f"-lat=-{abs(latitude)}"])
                else:
                    cmd.extend(["-lat", str(latitude)])
                
                # Use the -lon=VALUE format for negative longitude values
                if longitude < 0:
                    cmd.extend([f"-lon=-{abs(longitude)}"])
                else:
                    cmd.extend(["-lon", str(longitude)])
                
                cmd.extend(["-r", str(radius)])
            
            if only_with_power:
                cmd.extend(["-p", str(min_power)])
            
            if six_digit:
                cmd.extend(["-6"])
            
            cmd.extend(["-zc", str(zone_capacity)])
            
            if customize:
                cmd.extend(["-c"])
            
            if callsign_filter:
                cmd.extend(["-cs", callsign_filter])
            
            # Show command
            cmd_str = " ".join(cmd)
            st.code(cmd_str, language="bash")
            
            # Run command
            with st.spinner("Generating zone files..."):
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
                output, error = process.communicate()
                
                if process.returncode == 0:
                    st.success("Zone files generated successfully!")
                    st.code(output)
                    
                    # Find generated XML files in user-specific output directory
                    output_dir = f"output_{session_id}"
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    xml_files = [f for f in os.listdir(output_dir) if f.endswith('.xml')]
                    
                    if xml_files:
                        st.subheader("Download Generated Files")
                        
                        # Create a zip file with all generated files
                        import io
                        import zipfile
                        
                        # Create a download button for all files in a zip
                        if xml_files:
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                # Add all XML files
                                for xml_file in xml_files:
                                    file_path = os.path.join(output_dir, xml_file)
                                    with open(file_path, "r") as file:
                                        zip_file.writestr(xml_file, file.read())
                            
                            # Create download button for the zip file
                            zip_buffer.seek(0)
                            zip_bytes = zip_buffer.getvalue()
                            zip_filename = f"mototrbo_files_{session_id[:8]}.zip"
                            st.download_button(
                                label="📦 Download All Files as ZIP",
                                data=zip_bytes,
                                file_name=zip_filename,
                                mime="application/zip",
                                key="download_standard_zip"
                            )
                            
                            # Horizontal line to separate individual file downloads
                            st.markdown("---")
                            st.markdown("Or download individual files:")
                        
                        # Individual file downloads
                        for xml_file in xml_files:
                            file_path = os.path.join(output_dir, xml_file)
                            with open(file_path, "r") as file:
                                file_content = file.read()
                                
                            b64 = base64.b64encode(file_content.encode()).decode()
                            href = f'<a href="data:application/octet-stream;base64,{b64}" download="{xml_file}">Download {xml_file}</a>'
                            st.markdown(href, unsafe_allow_html=True)
                    
                    # Clean up user-specific contact_uploads directory
                    user_uploads_dir = f"contact_uploads_{session_id}"
                    if os.path.exists(user_uploads_dir):
                        for file in os.listdir(user_uploads_dir):
                            file_path = os.path.join(user_uploads_dir, file)
                            try:
                                if os.path.isfile(file_path):
                                    os.unlink(file_path)
                            except Exception as e:
                                st.warning(f"Error deleting {file_path}: {e}")
                else:
                    st.error("Error generating zone files")
                    st.code(error)

with tab2:
    st.header("Talkgroup Mode")
    st.markdown("Create a zone file for each repeater with channels for talkgroups on the timeslots")
    
    # Create user-specific output directory using session ID
    user_output_dir = f"output_{session_id}"
    if not os.path.exists(user_output_dir):
        os.makedirs(user_output_dir)
    
    # Create download link for contact_template.csv
    template_href = ""
    if os.path.exists("contact_template.csv"):
        with open("contact_template.csv", "r") as file:
            template_content = file.read()
        template_b64 = base64.b64encode(template_content.encode()).decode()
        template_href = f'<a href="data:text/csv;base64,{template_b64}" download="contact_template.csv">contact_template.csv</a>'
    
    # Add file uploader for custom contact template
    st.subheader("Upload Custom Contact Template")
    st.markdown(f"Download and modify the {template_href} file if you want talkgroups named differently than Brandmeister", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload your own contact_template.csv", type="csv", key="tg_template_upload")
    if uploaded_file is not None:
        # Create user-specific contact_uploads directory
        user_uploads_dir = f"contact_uploads_{session_id}"
        if not os.path.exists(user_uploads_dir):
            os.makedirs(user_uploads_dir)
        
        # Save the uploaded file to user-specific directory
        template_path = os.path.join(user_uploads_dir, "contact_template.csv")
        with open(template_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # Also create a symlink in the contact_uploads directory for backward compatibility
        if not os.path.exists("contact_uploads"):
            os.makedirs("contact_uploads")
        try:
            # Remove any existing file first
            contact_uploads_path = os.path.join("contact_uploads", "contact_template.csv")
            if os.path.exists(contact_uploads_path):
                os.remove(contact_uploads_path)
            # Copy the file instead of creating a symlink (more compatible)
            import shutil
            shutil.copy2(template_path, contact_uploads_path)
        except Exception as e:
            st.warning(f"Could not create backup of template: {e}")
        st.success("Custom contact template uploaded successfully!")
        
        # Display the uploaded file as a dataframe
        try:
            df = pd.read_csv(uploaded_file)
            st.dataframe(df, height=200)
        except:
            st.warning("Could not display the uploaded file as a table")
    
    st.subheader("Channel Naming")
    use_city_prefix = st.checkbox("Use city abbreviation prefix for channel names", 
                                help="Prefix channel names with 3-character city abbreviation (e.g. 'NYC.TG123')")
    
    st.subheader("Search Settings")
    col1, col2 = st.columns(2)
    
    with col1:
        band_tg = st.selectbox("Band", ["vhf", "uhf"], help="Select repeater band", key="band_tg")
        
        search_type_tg = st.selectbox("Search Type", ["mcc", "qth", "gps"], 
                                     help="Select repeaters by MCC code, QTH locator index or GPS coordinates",
                                     key="search_type_tg")
        
        if search_type_tg == "mcc":
            mcc_tg = st.text_input("MCC Code or Country Code", 
                                  help="First repeater ID digits (usually 3 digits MCC) or two letter country code",
                                  key="mcc_tg")
        
        elif search_type_tg == "qth":
            qth_tg = st.text_input("QTH Locator", help="QTH locator index like KO26BX", key="qth_tg")
            radius_tg = st.number_input("Radius (km)", min_value=1, value=100, 
                                       help="Area radius in kilometers around the center of the chosen QTH locator",
                                       key="radius_tg")
            st.text(f"Equivalent: {radius_tg:.1f} km = {radius_tg * 0.621371:.1f} miles")
        
        elif search_type_tg == "gps":
            col_lat_tg, col_lon_tg = st.columns(2)
            with col_lat_tg:
                latitude_tg = st.number_input("Latitude", format="%.6f", key="latitude_tg")
            with col_lon_tg:
                longitude_tg = st.number_input("Longitude", format="%.6f", key="longitude_tg")
            radius_tg = st.number_input("Radius (km)", min_value=1, value=100, 
                                       help="Area radius in kilometers around the GPS coordinates",
                                       key="radius_tg")
            st.text(f"Equivalent: {radius_tg:.1f} km = {radius_tg * 0.621371:.1f} miles")
    
    with col2:
        force_download_tg = st.checkbox("Force Download", 
                                       help="Forcibly download repeater list even if it exists locally",
                                       key="force_download_tg")
        
        only_with_power_tg = st.checkbox("Only with Power", 
                                        help="Only select repeaters with defined power",
                                        key="only_with_power_tg")
        
        if only_with_power_tg:
            min_power_tg = st.number_input("Minimum Power (W)", min_value=1, value=10,
                                         help="Minimum power in watts", key="min_power_tg")
        
        six_digit_tg = st.checkbox("6-Digit ID Only", value=True,
                                  help="Only select repeaters with 6 digit ID (real repeaters, not hotspots)",
                                  key="six_digit_tg")
        
        callsign_filter_tg = st.text_input("Callsign Filter", 
                                          help="Only list callsigns containing specified string like a region number",
                                          key="callsign_filter_tg")
    
    if st.button("Generate Talkgroup Files", key="generate_talkgroup"):
        if search_type_tg == "mcc" and not mcc_tg:
            st.error("Please enter an MCC code or country code")
        elif search_type_tg == "qth" and not qth_tg:
            st.error("Please enter a QTH locator")
        elif search_type_tg == "gps" and (latitude_tg == 0 and longitude_tg == 0):
            st.error("Please enter valid GPS coordinates")
        else:
            # Build command with user-specific output directory
            user_output_dir = f"output_{session_id}"
            cmd = ["python", "zone.py", "-b", band_tg, "-t", search_type_tg, "-tg", "-o", user_output_dir]
            
            # Add city prefix option if selected
            if use_city_prefix:
                cmd.extend(["--city-prefix"])
            
            if force_download_tg:
                cmd.extend(["-f"])
            
            if search_type_tg == "mcc":
                cmd.extend(["-m", mcc_tg])
            elif search_type_tg == "qth":
                cmd.extend(["-q", qth_tg, "-r", str(radius_tg)])
            elif search_type_tg == "gps":
                # Handle negative coordinates using the format from README example
                if latitude_tg < 0:
                    cmd.extend([f"-lat=-{abs(latitude_tg)}"])
                else:
                    cmd.extend(["-lat", str(latitude_tg)])
                
                # Use the -lon=VALUE format for negative longitude values
                if longitude_tg < 0:
                    cmd.extend([f"-lon=-{abs(longitude_tg)}"])
                else:
                    cmd.extend(["-lon", str(longitude_tg)])
                
                cmd.extend(["-r", str(radius_tg)])
            
            if only_with_power_tg:
                cmd.extend(["-p", str(min_power_tg)])
            
            if six_digit_tg:
                cmd.extend(["-6"])
            
            if callsign_filter_tg:
                cmd.extend(["-cs", callsign_filter_tg])
            
            # Show command
            cmd_str = " ".join(cmd)
            st.code(cmd_str, language="bash")
            
            # Run command
            with st.spinner("Generating talkgroup files..."):
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
                output, error = process.communicate()
                
                if process.returncode == 0:
                    st.success("Talkgroup files generated successfully!")
                    st.code(output)
                    
                    # Find generated XML files and contacts.csv in user-specific output directory
                    output_dir = f"output_{session_id}"
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    xml_files = [f for f in os.listdir(output_dir) if f.endswith('.xml')]
                    
                    if xml_files:
                        st.subheader("Download Generated Zone Files")
                        
                        # Create a zip file with all generated files
                        import io
                        import zipfile
                        
                        # Create a download button for all files in a zip
                        if xml_files or os.path.exists(os.path.join(output_dir, "contacts.csv")):
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                # Add all XML files
                                for xml_file in xml_files:
                                    file_path = os.path.join(output_dir, xml_file)
                                    with open(file_path, "r") as file:
                                        zip_file.writestr(xml_file, file.read())
                                
                                # Add contacts.csv if it exists
                                contacts_file = os.path.join(output_dir, "contacts.csv")
                                if os.path.exists(contacts_file):
                                    with open(contacts_file, "r") as file:
                                        zip_file.writestr("contacts.csv", file.read())
                            
                            # Create download button for the zip file
                            zip_buffer.seek(0)
                            zip_bytes = zip_buffer.getvalue()
                            b64_zip = base64.b64encode(zip_bytes).decode()
                            zip_filename = f"mototrbo_files_{session_id[:8]}.zip"
                            st.download_button(
                                label="📦 Download All Files as ZIP",
                                data=zip_bytes,
                                file_name=zip_filename,
                                mime="application/zip",
                                key="download_all_zip"
                            )
                            
                            # Horizontal line to separate individual file downloads
                            st.markdown("---")
                            st.markdown("Or download individual files:")
                        
                        # Individual file downloads
                        for xml_file in xml_files:
                            file_path = os.path.join(output_dir, xml_file)
                            with open(file_path, "r") as file:
                                file_content = file.read()
                                
                            b64 = base64.b64encode(file_content.encode()).decode()
                            href = f'<a href="data:application/octet-stream;base64,{b64}" download="{xml_file}">Download {xml_file}</a>'
                            st.markdown(href, unsafe_allow_html=True)
                    
                    contacts_file = os.path.join(output_dir, "contacts.csv")
                    if os.path.exists(contacts_file):
                        st.subheader("Contacts CSV")
                        
                        # Display contacts as a table
                        try:
                            contacts_df = pd.read_csv(contacts_file)
                            st.dataframe(contacts_df)
                        except:
                            st.warning("Could not display contacts.csv as a table")
                        
                        # Provide download link
                        with open(contacts_file, "r") as file:
                            file_content = file.read()
                            
                        b64 = base64.b64encode(file_content.encode()).decode()
                        href = f'<a href="data:text/csv;base64,{b64}" download="contacts.csv">Download contacts.csv</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    
                    # Clean up user-specific contact_uploads directory
                    user_uploads_dir = f"contact_uploads_{session_id}"
                    if os.path.exists(user_uploads_dir):
                        for file in os.listdir(user_uploads_dir):
                            file_path = os.path.join(user_uploads_dir, file)
                            try:
                                if os.path.isfile(file_path):
                                    os.unlink(file_path)
                            except Exception as e:
                                st.warning(f"Error deleting {file_path}: {e}")
                else:
                    st.error("Error generating talkgroup files")
                    st.code(error)

# Help section
st.sidebar.header("Help")

st.sidebar.markdown("""
## How to use
1. Choose between Standard Mode or Talkgroup Mode
2. Fill in the required fields
3. In Talkgroup Mode, upload a custom contact template if needed
4. Click the Generate button
5. Download the generated files
""", unsafe_allow_html=True)

st.sidebar.markdown("""
## Importing to CPS2
### Zone Files
- Open the XML file in a text editor
- Select All and Copy
- In CPS2, go to Configuration - Zone/Channel Assignment
- Right-click on Zone and choose Paste

### Contacts (Talkgroup Mode)
- In CPS2, go to Contacts - Digital
- Click Import and select the contacts.csv file
""")

# About section
st.sidebar.header("About")
st.sidebar.markdown("""
MOTOTRBO Zone Generator uses the [BrandMeister API](https://wiki.brandmeister.network/index.php/API/Halligan_API) to retrieve DMR repeater information and generate zone files for Motorola DMR radios.

[View on GitHub](https://github.com/GitEric77/MotoBM)
""")
[Demo Video](https://youtu.be/cRO7uoUekoY)
""")

# Display session ID in sidebar for debugging (can be removed in production)
st.sidebar.header("Session Info")
st.sidebar.text(f"Session ID: {session_id[:8]}...")