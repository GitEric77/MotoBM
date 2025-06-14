# MOTOTRBO Zone Generator - Streamlit Frontend

This is a web-based frontend for the MOTOTRBO zone file generator that uses the BrandMeister API to retrieve DMR repeater information and generate zone files for Motorola DMR radios.

## Installation

1. Make sure you have all the required dependencies installed:
   ```
   pip install -r requirements_streamlit.txt
   ```

2. Run the Streamlit app:
   ```
   streamlit run app.py
   ```

3. The app will open in your default web browser at http://localhost:8501

## Features

- **User-friendly interface** for generating MOTOTRBO zone files
- **Standard Mode** for creating zone files with all repeaters
- **Talkgroup Mode** for creating zone files with active talkgroups and respective contacts
- **Download** generated XML files and contacts.csv directly from the browser
- **Bulk Download** all generated files in a single ZIP archive
- **City Prefix** option to name channels with city abbreviation and talkgroup name
- **Unique Session IDs** for multiple users to work simultaneously
- **Visualize** zone file and contact output in the web interface

## Usage

### Standard Mode
1. Enter a zone name
2. Select the band (VHF or UHF)
3. Choose a search type (MCC, QTH, or GPS)
4. Fill in the required fields based on your search type
5. Configure additional options as needed
6. Click "Generate Zone Files"
7. Download the generated XML file or as a ZIP archive

### Talkgroup Mode
1. Select the band (VHF or UHF)
2. Choose a search type (MCC, QTH, or GPS)
3. Fill in the required fields based on your search type
4. Optionally enable "Use city abbreviation prefix for channel names" to add city prefixes to channels Ex: BUR.MN State
5. Configure additional options as needed
6. Click "Generate Talkgroup Files"
7. Download the generated XML files and contacts.csv individually or as a ZIP archive

### Custom Contact Template
1. Download the default contact_template.csv
2. Modify the template with your preferred contact names (ensure to specify Group Call or Private Call)
3. Upload your modified template using the "Upload Custom Contact Template"
4. Your custom template will be used when generating talkgroup files

## Importing to CPS2
!!!You must import contacts prior to pasting zone files!!!
### Contacts (Talkgroup Mode)
1. In CPS2, go to Contacts → Contacts, click on button with three dots above contacts list and select import
2. Select the contacts.csv file

### Zone Files
1. Open the XML file in a text editor
2. Select all data in XML file and copy (Ctrl+a, Ctrl+c)
3. In CPS2, go to Configuration → Zone/Channel Assignment
4. Right-click on word Zone and choose paste (Ctrl+v)