#!/usr/bin/env python3

import argparse
import json
from os.path import exists
from tabulate import tabulate

import geopy.distance
import maidenhead
import mobile_codes
import requests
import urllib3


parser = argparse.ArgumentParser(description='Generate MOTOTRBO zone files from BrandMeister.')

parser.add_argument('-f', '--force', action='store_true',
                    help='Forcibly download repeater list even if it exists locally.')
parser.add_argument('-n', '--name', required=False, help='Zone name. Choose it freely on your own. Required unless using -tg argument.')
parser.add_argument('-b', '--band', choices=['vhf', 'uhf'], required=True, help='Repeater band.')

parser.add_argument('-t', '--type', choices=['mcc', 'qth', 'gps'], required=True,
                    help='Select repeaters by MCC code, QTH locator index or GPS coordinates.')

parser.add_argument('-m', '--mcc', help='First repeater ID digits, usually a 3 digits MCC. '
                                        'You can also use a two letter country code instead.')
parser.add_argument('-q', '--qth', help='QTH locator index like KO26BX.')

parser.add_argument('-r', '--radius', default=100, type=int,
                    help='Area radius in kilometers around the center of the chosen QTH locator. Defaults to 100.')

parser.add_argument('-lat', type=float, help='Latitude of a GPS position.')
parser.add_argument('-lon', type=float, help='Longitude of a GPS position.')

parser.add_argument('-p', '--pep', nargs='?', const='0', help='Only select repeaters with defined power. Optional value specifies minimum power in watts.')
parser.add_argument('-6', '--six', action='store_true', help='Only select repeaters with 6 digit ID.')
parser.add_argument('-zc', '--zone-capacity', default=160, type=int,
                    help='Channel capacity within zone. 160 by default as for top models, use 16 for the lite and '
                         'non-display ones.')
parser.add_argument('-c', '--customize', action='store_true',
                    help='Include customized values for each channel.')
parser.add_argument('-cs', '--callsign', help='Only list callsigns containing specified string like a region number.')
parser.add_argument('-tg', '--talkgroups', action='store_true',
                    help='Create channels only for active talkgroups on repeaters (no channels with blank contact ID).')
parser.add_argument('-o', '--output', default='output',
                    help='Output directory for generated files. Default is "output".')


args = parser.parse_args()

# Validate that name is provided if not using talkgroups mode
if not args.name and not args.talkgroups:
    parser.error("the -n/--name argument is required when not using -tg/--talkgroups")


bm_url = 'https://api.brandmeister.network/v2/device'
bm_file = 'BM.json'
filtered_list = []
output_list = []
existing = {}
custom_file = 'custom-values.xml'
custom_values = ''

if args.type == 'qth':
    qth_coords = maidenhead.to_location(args.qth, center=True)
if args.type == 'gps':
    qth_coords = (args.lat, args.lon)

if args.mcc and not str(args.mcc).isdigit():
    args.mcc = mobile_codes.alpha2(args.mcc)[4]


def check_custom():
    global custom_file
    global custom_values

    if not exists(custom_file):
        with open(custom_file, 'w') as file:
            file.write('')

    with open(custom_file, 'r') as file:
        custom_values = file.read()


def download_file():
    if not exists(bm_file) or args.force:
        print(f'Downloading from {bm_url}')

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.get(bm_url, verify=False)
        response.raise_for_status()

        with open(bm_file, 'wb') as file:
            file.write(response.content)

        print(f'Saved to {bm_file}')


def check_distance(loc1, loc2):
    return geopy.distance.great_circle(loc1, loc2).km


def filter_list():
    global filtered_list
    global existing
    global qth_coords

    f = open(bm_file, "r")

    json_list = json.loads(f.read())
    sorted_list = sorted(json_list, key=lambda k: (k['callsign'], int(k["id"])))

    for item in sorted_list:
        if not ((args.band == 'vhf' and item['rx'].startswith('1')) or (
                args.band == 'uhf' and item['rx'].startswith('4'))):
            continue

        if args.type == 'mcc':
            is_starts = False

            if type(args.mcc) is list:
                for mcc in args.mcc:
                    if str(item['id']).startswith(mcc):
                        is_starts = True
            else:
                if str(item['id']).startswith(args.mcc):
                    is_starts = True

            if not is_starts:
                continue

        if (args.type == 'qth' or args.type == 'gps') and check_distance(qth_coords,
                                                                         (item['lat'], item['lng'])) > args.radius:
            continue

        if args.pep:
            # Skip if power is not defined or is zero
            if not str(item['pep']).isdigit() or str(item['pep']) == '0':
                continue
            # Skip if power is less than specified minimum (if provided)
            if args.pep != '0' and int(item['pep']) < int(args.pep):
                continue

        if args.six and not len(str(item['id'])) == 6:
            continue

        if args.callsign and (not args.callsign in item['callsign']):
            continue

        if item['callsign'] == '':
            item['callsign'] = item['id']

        item['callsign'] = item['callsign'].split()[0]

        if any((existing['rx'] == item['rx'] and existing['tx'] == item['tx'] and existing['callsign'] == item[
            'callsign']) for existing in filtered_list):
            continue

        if not item['callsign'] in existing: existing[item['callsign']] = 0
        existing[item['callsign']] += 1
        item['turn'] = existing[item['callsign']]

        filtered_list.append(item)

    f.close()


def get_talkgroup_channels(repeater_id):
    """
    Get talkgroups for a specific repeater from BrandMeister API
    
    Args:
        repeater_id (int): Repeater ID
        
    Returns:
        list: List of talkgroup IDs configured for this repeater
    """
    try:
        url = f'https://api.brandmeister.network/v2/device/{repeater_id}/talkgroup'
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, verify=False)
        response.raise_for_status()
        talkgroups_data = response.json()
        
        # Extract talkgroup IDs
        tg_ids = []
        for tg in talkgroups_data:
            if 'talkgroup' in tg and tg.get('slot') is not None:
                tg_ids.append((tg['talkgroup'], tg['slot']))
        
        return tg_ids
    except Exception as e:
        print(f"Error fetching talkgroups for repeater {repeater_id}: {e}")
        return []


def format_talkgroup_channel(item, tg_id, timeslot):
    """Format a channel for a specific talkgroup"""
    global custom_values
    global output_list
    
    # Check if talkgroup ID exists in contacts.csv
    contact_name = None
    try:
        import csv
        import os
        contacts_file = os.path.join(args.output, 'contacts.csv')
        if os.path.exists(contacts_file):
            with open(contacts_file, 'r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                next(reader)  # Skip header row 1
                next(reader)  # Skip header row 2
                for row in reader:
                    if len(row) > 25 and row[25] == str(tg_id) and row[0]:  # Check if column A has a value
                        contact_name = row[0]
                        break
    except Exception:
        pass
    
    # If talkgroup ID is not in contacts.csv or column A is empty, fetch from BrandMeister API
    tg_name = None
    if not contact_name:
        try:
            url = f'https://api.brandmeister.network/v2/talkgroup/{tg_id}'
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, verify=False)
            response.raise_for_status()
            data = response.json()
            if 'Name' in data and data['Name']:
                tg_name = data['Name']
        except Exception:
            pass
    
    # Use contact name from contacts.csv if available, otherwise use talkgroup name from API or talkgroup ID
    if contact_name:
        ch_alias = f"{contact_name}"[:16]  # Limit to 16 characters
        ukp_value = str(contact_name)[:16]  # Limit to 16 characters
    elif tg_name:
        ch_alias = f"{tg_name}"[:16]  # Limit to 16 characters
        ukp_value = str(tg_name)[:16]  # Limit to 16 characters
    else:
        ch_alias = f"TG{tg_id}"[:16]  # Limit to 16 characters
        ukp_value = str(tg_id)[:16]  # Limit to 16 characters
    
    ch_rx = item['rx']
    ch_tx = item['tx']
    ch_cc = item['colorcode']
    
    # Add to output list for display
    output_list.append([item['callsign'], ch_rx, ch_tx, ch_cc, item['city'], item['last_seen'],
                        f"https://brandmeister.network/?page=repeater&id={item['id']} TG{tg_id}"])
    
    return f'''
<set name="ConventionalPersonality" alias="{ch_alias}" key="DGTLCONV6PT25">
  <field name="CP_PERSTYPE" Name="Digital">DGTLCONV6PT25</field>
  <field name="CP_SLTASSGMNT" Name="{timeslot}">SLOT{timeslot}</field>
  <field name="CP_COLORCODE">{ch_cc}</field>
  <field name="CP_TXFREQ">{ch_rx}</field>
  <field name="CP_RXFREQ">{ch_tx}</field>
  <field name="CP_EMACKALERTEN">True</field>
  <field name="CP_CNVPERSALIAS">{ch_alias}</field>
  <field name="CP_TXINHXPLEN" Name="Color Code Free">MTCHCLRCD</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_GPSRVRTPERSIT" Name="Selected">SELECTED</field>
  <field name="CP_OVCMDECODEENABLE">True</field>
  <field name="CP_TXCOMPUDPIPHEADEN" Name="DMR Standard">DMR_UDP_HEADER</field>
  <field name="CP_LOCATIONDATADELIVERYMODE" Name="Follow Data Call Confirmed">FOLLOW_CALL_DATA_SETTING</field>
  <field name="CP_MYCALLADCRTR" Name="Follow Admit Criteria">FOLLOW_ADMIT_CRITERIA</field>
  <field name="CP_TEXTMESSAGETYPE" Name="Advantage">TMS</field>
  <field name="CP_TRANSMITINTERRUPTTYPE" Name="Advantage">PROPRIETARY</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_TOT">180</field>
  <field name="CP_RASDATAITEM" Name="None">None</field>
  <field name="CP_INTRPTMSGDLY">510</field>
  <field name="CP_UKPPERS" Name="{ukp_value}">{ukp_value}</field>
{custom_values}
</set>
    '''


def format_channel(item):
    global existing
    global output_list
    global custom_values

    if existing[item['callsign']] == 1:
        ch_alias = item['callsign']
    else:
        ch_alias = f"{item['callsign']} #{item['turn']}"

    ch_rx = item['rx']
    ch_tx = item['tx']
    ch_cc = item['colorcode']

    output_list.append([ch_alias, ch_rx, ch_tx, ch_cc, item['city'], item['last_seen'],
                        f"https://brandmeister.network/?page=repeater&id={item['id']}"])

    if item['rx'] == item['tx']:
        return f'''
<set name="ConventionalPersonality" alias="{ch_alias}" key="DGTLCONV6PT25">
  <field name="CP_PERSTYPE" Name="Digital">DGTLCONV6PT25</field>
  <field name="CP_SLTASSGMNT" Name="2">SLOT2</field>
  <field name="CP_COLORCODE">{ch_cc}</field>
  <field name="CP_TXFREQ">{ch_rx}</field>
  <field name="CP_RXFREQ">{ch_tx}</field>
  <field name="CP_EMACKALERTEN">True</field>
  <field name="CP_CNVPERSALIAS">{ch_alias}</field>
  <field name="CP_TXINHXPLEN" Name="Color Code Free">MTCHCLRCD</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_GPSRVRTPERSIT" Name="Selected">SELECTED</field>
  <field name="CP_OVCMDECODEENABLE">True</field>
  <field name="CP_TXCOMPUDPIPHEADEN" Name="DMR Standard">DMR_UDP_HEADER</field>
  <field name="CP_LOCATIONDATADELIVERYMODE" Name="Follow Data Call Confirmed">FOLLOW_CALL_DATA_SETTING</field>
  <field name="CP_MYCALLADCRTR" Name="Follow Admit Criteria">FOLLOW_ADMIT_CRITERIA</field>
  <field name="CP_TEXTMESSAGETYPE" Name="Advantage">TMS</field>
  <field name="CP_TRANSMITINTERRUPTTYPE" Name="Advantage">PROPRIETARY</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_TOT">180</field>
  <field name="CP_INTRPTMSGDLY">510</field>
{custom_values}
</set>
    '''

    return f'''
<set name="ConventionalPersonality" alias="{ch_alias} TS1" key="DGTLCONV6PT25">
  <field name="CP_PERSTYPE" Name="Digital">DGTLCONV6PT25</field>
  <field name="CP_SLTASSGMNT" Name="1">SLOT1</field>
  <field name="CP_COLORCODE">{ch_cc}</field>
  <field name="CP_TXFREQ">{ch_rx}</field>
  <field name="CP_RXFREQ">{ch_tx}</field>
  <field name="CP_EMACKALERTEN">True</field>
  <field name="CP_CNVPERSALIAS">{ch_alias} TS1</field>
  <field name="CP_TXINHXPLEN" Name="Color Code Free">MTCHCLRCD</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_GPSRVRTPERSIT" Name="Selected">SELECTED</field>
  <field name="CP_OVCMDECODEENABLE">True</field>
  <field name="CP_TXCOMPUDPIPHEADEN" Name="DMR Standard">DMR_UDP_HEADER</field>
  <field name="CP_LOCATIONDATADELIVERYMODE" Name="Follow Data Call Confirmed">FOLLOW_CALL_DATA_SETTING</field>
  <field name="CP_MYCALLADCRTR" Name="Follow Admit Criteria">FOLLOW_ADMIT_CRITERIA</field>
  <field name="CP_TEXTMESSAGETYPE" Name="Advantage">TMS</field>
  <field name="CP_TRANSMITINTERRUPTTYPE" Name="Advantage">PROPRIETARY</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_ARSPLUS" Name="On System/Site Change">ARS_SYS_SITE_CHANGE</field>
  <field name="CP_TOT">180</field>
  <field name="CP_INTRPTMSGDLY">510</field>
{custom_values}
</set>
<set name="ConventionalPersonality" alias="{ch_alias} TS2" key="DGTLCONV6PT25">
  <field name="CP_PERSTYPE" Name="Digital">DGTLCONV6PT25</field>
  <field name="CP_SLTASSGMNT" Name="2">SLOT2</field>
  <field name="CP_COLORCODE">{ch_cc}</field>
  <field name="CP_TXFREQ">{ch_rx}</field>
  <field name="CP_RXFREQ">{ch_tx}</field>
  <field name="CP_EMACKALERTEN">True</field>
  <field name="CP_CNVPERSALIAS">{ch_alias} TS2</field>
  <field name="CP_TXINHXPLEN" Name="Color Code Free">MTCHCLRCD</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_GPSRVRTPERSIT" Name="Selected">SELECTED</field>
  <field name="CP_OVCMDECODEENABLE">True</field>
  <field name="CP_TXCOMPUDPIPHEADEN" Name="DMR Standard">DMR_UDP_HEADER</field>
  <field name="CP_LOCATIONDATADELIVERYMODE" Name="Follow Data Call Confirmed">FOLLOW_CALL_DATA_SETTING</field>
  <field name="CP_MYCALLADCRTR" Name="Follow Admit Criteria">FOLLOW_ADMIT_CRITERIA</field>
  <field name="CP_TEXTMESSAGETYPE" Name="Advantage">TMS</field>
  <field name="CP_TRANSMITINTERRUPTTYPE" Name="Advantage">PROPRIETARY</field>
  <field name="CP_MLTSTPSNLTIND">True</field>
  <field name="CP_ARSPLUS" Name="On System/Site Change">ARS_SYS_SITE_CHANGE</field>
  <field name="CP_TOT">180</field>
  <field name="CP_INTRPTMSGDLY">510</field>
{custom_values}
</set>
    '''


def cleanup_contact_uploads():
    """Delete files in the contact_uploads directory after processing"""
    import os
    
    # Clean up regular contact_uploads directory
    if exists('contact_uploads'):
        for file in os.listdir('contact_uploads'):
            file_path = os.path.join('contact_uploads', file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    print(f"Deleted {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
    
    # Clean up user-specific contact_uploads directories
    for dir_name in os.listdir('.'):
        if dir_name.startswith('contact_uploads_'):
            for file in os.listdir(dir_name):
                file_path = os.path.join(dir_name, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                        print(f"Deleted {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")


def process_channels():
    global output_list

    if args.talkgroups:
        # Collect all unique talkgroup IDs first
        unique_talkgroups = set()
        
        # First pass: collect all talkgroup IDs
        for item in filtered_list:
            try:
                tg_channels = get_talkgroup_channels(item['id'])
                for tg_id, slot in tg_channels:
                    unique_talkgroups.add(tg_id)
            except Exception as e:
                print(f"Error collecting talkgroups for {item['callsign']}: {e}")
        
        # Process contacts.csv first to ensure it exists with all needed talkgroups
        try:
            import csv
            import time
            import os
            import shutil
            
            # Create output directory if it doesn't exist
            if not os.path.exists(args.output):
                os.makedirs(args.output)
            
            contacts_file = os.path.join(args.output, 'contacts.csv')
            
            # Check for custom template in user-specific contact_uploads directory first
            user_uploads_dir = None
            for dir_name in os.listdir('.'):
                if dir_name.startswith('contact_uploads_'):
                    user_uploads_dir = dir_name
                    break
                    
            if user_uploads_dir:
                custom_template = os.path.join(user_uploads_dir, 'contact_template.csv')
                if exists(custom_template):
                    try:
                        shutil.copy(custom_template, contacts_file)
                        print(f"Copied custom contact_template.csv from {user_uploads_dir} to {contacts_file}")
                        # Template found and copied, skip to next section
                    except Exception as e:
                        print(f"Error copying custom contact template from {user_uploads_dir}: {e}")
            
            # Then check regular contact_uploads directory
            custom_template = os.path.join('contact_uploads', 'contact_template.csv')
            if exists(custom_template) and not exists(contacts_file):
                try:
                    shutil.copy(custom_template, contacts_file)
                    print(f"Copied custom contact_template.csv from contact_uploads to {contacts_file}")
                except Exception as e:
                    print(f"Error copying custom contact template: {e}")
            # Fall back to default template if no custom template exists
            elif exists('contact_template.csv') and not exists(contacts_file):
                try:
                    shutil.copy('contact_template.csv', contacts_file)
                    print(f"Copied default contact_template.csv to {contacts_file}")
                except Exception as e:
                    print(f"Error copying default contact template: {e}")
            
            # Create empty contacts file if it doesn't exist
            if not exists(contacts_file):
                with open(contacts_file, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["ContactName", "Delete_Contact", "Rename_Contact", "Comments", "Delete_FiveToneCalls", 
                                    "FiveToneCalls-S5CLDLL_5TTELEGRAM", "FiveToneCalls-S5CLDLL_5TCALLADD", "Delete_MDCCalls", 
                                    "MDCCalls-AU_CALLLSTID", "MDCCalls-AU_MDCSYS", "MDCCalls-AU_RVRTPERS_Zone", 
                                    "MDCCalls-AU_RVRTPERS", "MDCCalls-AU_SPTPLDPL", "MDCCalls-AU_CALLTYPE", 
                                    "Delete_QuikCallIICalls", "QuikCallIICalls-QU_QCIISYS", "QuikCallIICalls-QU_RVRTPERS_Zone", 
                                    "QuikCallIICalls-QU_RVRTPERS", "QuikCallIICalls-QU_CALLFORMAT", "QuikCallIICalls-QU_TONEATXFRE", 
                                    "QuikCallIICalls-QU_CODEA", "QuikCallIICalls-QU_TONEBTXFRE", "QuikCallIICalls-QU_CODEB", 
                                    "QuikCallIICalls-QU_STRIPPLDPL", "Delete_DigitalCalls", "DigitalCalls-DU_CALLLSTID", 
                                    "DigitalCalls-DU_ROUTETYPE", "DigitalCalls-DU_CALLPRCDTNEN", "DigitalCalls-DU_RINGTYPE", 
                                    "DigitalCalls-DU_TXTMSGALTTNTP", "DigitalCalls-DU_CALLTYPE"])
                    writer.writerow(["Contact Name", "Delete_Contact", "Rename_Contact", "Comments", "Delete_FiveToneCalls", 
                                    "Five Tone Calls - Telegram", "Five Tone Calls - Address", "Delete_MDCCalls", 
                                    "MDC Calls - Call ID (Hex)", "MDC Calls - MDC System", "MDC Calls - Revert Channel Zone", 
                                    "MDC Calls - Revert Channel", "MDC Calls - Strip TPL/DPL", "MDC Calls - Call Type", 
                                    "Delete_QuikCallIICalls", "Quik CallII Calls - Quik-Call II System", 
                                    "Quik CallII Calls - Revert Channel Zone", "Quik CallII Calls - Revert Channel", 
                                    "Quik CallII Calls - Call Format", "Quik CallII Calls - Tone A Freq (Hz)", 
                                    "Quik CallII Calls - Tone A Code", "Quik CallII Calls - Tone B Freq (Hz)", 
                                    "Quik CallII Calls - Tone B Code", "Quik CallII Calls - Strip TPL/DPL", 
                                    "Delete_DigitalCalls", "Digital Calls - Call ID", "Digital Calls - Route Type", 
                                    "Digital Calls - Call Receive Tone", "Digital Calls - Ring Style", 
                                    "Digital Calls - Text Message Alert Tone", "Digital Calls - Call Type"])
            
            # Read the existing CSV file
            with open(contacts_file, 'r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
            
            # Keep the header rows (first 2 rows)
            header_rows = rows[:2]
            template_row = rows[2] if len(rows) > 2 else [''] * len(header_rows[0])
            
            # Get existing talkgroup IDs to avoid duplicates
            existing_tg_ids = set()
            for row in rows[2:]:  # Skip header rows
                if len(row) > 25 and row[25]:  # Check if column Z has a value
                    existing_tg_ids.add(row[25])
            
            # Create new rows with talkgroup data
            new_rows = []
            for tg_id in sorted(unique_talkgroups):
                # Extract only numeric characters from talkgroup ID
                numeric_tg_id = ''.join(c for c in str(tg_id) if c.isdigit())
                if numeric_tg_id and numeric_tg_id not in existing_tg_ids:  # Only add if not already in contacts
                    new_row = template_row.copy() if template_row else [''] * len(header_rows[0])
                    new_row[25] = numeric_tg_id    # Column Z: DigitalCalls-DU_CALLLSTID
                    
                    # Check if this talkgroup ID already exists in contacts.csv with a name
                    existing_name = None
                    for row in rows[2:]:  # Skip header rows
                        if len(row) > 25 and row[25] == numeric_tg_id and row[0]:
                            existing_name = row[0]
                            break
                    
                    if existing_name:
                        # Use existing name from contacts.csv
                        new_row[0] = existing_name
                        print(f"Using existing name for TG {numeric_tg_id}: {existing_name}")
                    else:
                        # Fetch talkgroup name from BrandMeister API
                        try:
                            print(f"Fetching name for TG {numeric_tg_id}...", end="", flush=True)
                            url = f'https://api.brandmeister.network/v2/talkgroup/{numeric_tg_id}'
                            response = requests.get(url, verify=False)
                            response.raise_for_status()
                            data = response.json()
                            if 'Name' in data and data['Name']:
                                new_row[0] = data['Name']  # Column A: ContactName from API
                                print(f" Found: {data['Name']}")
                            else:
                                new_row[0] = numeric_tg_id  # Fallback to ID if no name
                                print(" No name found")
                            time.sleep(0.2)  # Be nice to the API
                        except Exception as api_error:
                            print(f"\nError fetching name for TG {numeric_tg_id}: {api_error}")
                            new_row[0] = numeric_tg_id  # Fallback to ID if API fails
                    
                    # Make sure row has enough columns
                    while len(new_row) <= 30:
                        new_row.append("")
                    # Set column AE (index 30) to "Group Call"
                    new_row[30] = "Group Call"
                    new_rows.append(new_row)
            
            # Write the updated CSV file with existing entries plus new ones
            with open(contacts_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(header_rows)
                writer.writerows(rows[2:])  # Write existing entries after headers
                writer.writerows(new_rows)  # Append new unique entries
            
            print(f"Updated {contacts_file} with {len(new_rows)} new unique talkgroups (total: {len(rows[2:]) + len(new_rows)})")
        except Exception as e:
            print(f"Error updating contacts.csv: {e}")
        
        # Now create channels using the updated contacts.csv
        for item in filtered_list:
            channels = ''
            output_list = []
            
            try:
                tg_channels = get_talkgroup_channels(item['id'])
                if not tg_channels:
                    continue  # Skip repeaters with no talkgroups
                    
                for tg_id, slot in tg_channels:
                    channels += format_talkgroup_channel(item, tg_id, slot)
                
                # Use city name for zone name
                city = item['city'].split(',')[0].strip()
                callsign = item['callsign']
                
                # Create filename (can be longer)
                filename = f"{callsign}_{city.replace(' ', '_')}"
                
                # Create zone alias (must be 16 chars or less)
                if len(callsign) + 1 >= 16:
                    # If callsign is already too long, just use it
                    zone_alias = callsign[:16]
                else:
                    # Use remaining space for city
                    city_max_len = 15 - len(callsign)
                    city_abbr = city.replace(' ', '')[:city_max_len]
                    zone_alias = f"{callsign}_{city_abbr}"
                # Ensure it's exactly 16 chars or less
                zone_alias = zone_alias[:16]
                
                print('\n',
                      tabulate(output_list, headers=['Callsign', 'RX', 'TX', 'CC', 'City', 'Last seen', 'URL'],
                               disable_numparse=True),
                      '\n')
                
                write_zone_file(filename, f'''<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>
<config>
  <category name=\"Zone\">
    <set name=\"Zone\" alias=\"{zone_alias}\" key=\"NORMAL\">
      <collection name=\"ZoneItems\">
        {channels}
      </collection>
      <field name=\"ZP_ZONEALIAS\">{zone_alias}</field>
      <field name=\"ZP_ZONETYPE\" Name=\"Normal\">NORMAL</field>
      <field name=\"ZP_ZVFNLITEM\" Name=\"None\">NONE</field>
      <field name=\"Comments\"></field>
    </set>
  </category>
</config>
''')
            except Exception as e:
                print(f"Error processing talkgroups for {item['callsign']}: {e}")
        

    else:
        # Original behavior for non-talkgroup mode
        channel_chunks = [filtered_list[i:i + args.zone_capacity] for i in range(0, len(filtered_list), args.zone_capacity)]
        chunk_number = 0

        for chunk in channel_chunks:
            channels = ''
            chunk_number += 1
            output_list = []

            for item in chunk:
                channels += format_channel(item)

            print('\n',
                  tabulate(output_list, headers=['Callsign', 'RX', 'TX', 'CC', 'City', 'Last seen', 'URL'],
                           disable_numparse=True),
                  '\n')

            if len(channel_chunks) == 1:
                zone_alias = args.name
            else:
                zone_alias = f'{args.name} #{chunk_number}'

            write_zone_file(zone_alias, f'''<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>
<config>
  <category name=\"Zone\">
    <set name=\"Zone\" alias=\"{zone_alias}\" key=\"NORMAL\">
      <collection name=\"ZoneItems\">
        {channels}
      </collection>
      <field name=\"ZP_ZONEALIAS\">{zone_alias}</field>
      <field name=\"ZP_ZONETYPE\" Name=\"Normal\">NORMAL</field>
      <field name=\"ZP_ZVFNLITEM\" Name=\"None\">NONE</field>
      <field name=\"Comments\"></field>
    </set>
  </category>
</config>
''')


def write_zone_file(zone_alias, contents):
    import os
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    zone_file_name = os.path.join(args.output, zone_alias + ".xml")
    zone_file = open(zone_file_name, "wt")
    zone_file.write(contents)
    zone_file.close()
    print(f'Zone file "{zone_file_name}" written.\n')


if __name__ == '__main__':
    if args.customize:
        check_custom()
    download_file()
    filter_list()
    process_channels()
    cleanup_contact_uploads()