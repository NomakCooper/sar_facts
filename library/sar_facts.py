#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2025 Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: sar_facts
short_description: Collect system activity report (SAR) data for system performance monitoring.
description:
  - Retrieves SAR data using the `sar` command from system logs.
  - Supports filtering by date range, time range, and partition details.
  - Returns performance metrics such as CPU utilization, memory usage, disk activity, and network statistics.
options:
  date_start:
    description: Start date for collecting SAR data (format YYYY-MM-DD).
    required: false
    type: str
  date_end:
    description: End date for collecting SAR data (format YYYY-MM-DD).
    required: false
    type: str
  time_start:
    description: Start time for collecting SAR data (format HH:MM:SS).
    required: false
    type: str
  time_end:
    description: End time for collecting SAR data (format HH:MM:SS).
    required: false
    type: str
  type:
    description: Type of SAR data to retrieve.
    choices: [ cpu, memory, swap, network, disk, load ]
    required: true
    type: str
  average:
    description: Whether to retrieve only the average values.
    required: false
    type: bool
    default: false
  partition:
    description: Whether to retrieve partition-specific disk statistics.
    required: false
    type: bool
    default: false
author:
  - Marco Noce (@NomakCooper)
'''

from ansible.module_utils.basic import AnsibleModule
import os
import subprocess
from datetime import datetime, timedelta

SAR_LOG_PATHS = ["/var/log/sa/", "/var/log/sysstat/"]
SAR_BIN_PATHS = ["/usr/bin/sar", "/usr/sbin/sar", "/bin/sar"]

SAR_FACT_MAPPING = {
    "cpu": "sar_cpu",
    "memory": "sar_mem",
    "swap": "sar_swap",
    "network": "sar_net",
    "disk": "sar_disk",
    "load": "sar_load"
}


def locate_sar():
    """Finds the SAR binary in the system."""
    for path in SAR_BIN_PATHS:
        if os.path.exists(path):
            return path
    return None


def find_sar_file(date_str):
    """Finds the SAR log file for a given date."""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day = date_obj.strftime("%d")

        for path in SAR_LOG_PATHS:
            file_path = os.path.join(path, f"sa{day}")
            if os.path.exists(file_path):
                return file_path

    except ValueError:
        return None

    return None


def run_sar_command(module, sar_bin, sar_file, sar_type, time_start, time_end, partition, average, date_str):
    """Executes the SAR command and returns parsed results."""
    command = [sar_bin, "-f", sar_file]

    sar_flags = {
        "cpu": ["-u"],
        "memory": ["-r"],
        "swap": ["-S"],
        "network": ["-n", "DEV"],
        "disk": ["-d", "-p"] if partition else ["-d"],
        "load": ["-q"],
    }

    if sar_type in sar_flags:
        command.extend(sar_flags[sar_type])

    if time_start:
        command.extend(["-s", time_start])
    if time_end:
        command.extend(["-e", time_end])

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return parse_sar_output(result.stdout, sar_type, average, date_str)
    except subprocess.CalledProcessError as e:
        module.fail_json(msg=f"Failed to execute SAR command: {str(e)}")

# Aggiunta della funzione convert_to_24h per la conversione di orario 12H a 24H.
def convert_to_24h(time_str, am_pm):
    return datetime.strptime(f"{time_str} {am_pm}", "%I:%M:%S %p").strftime("%H:%M:%S")

def parse_sar_output(output, sar_type, average, date_str):
    """Parses SAR output by finding the header line and converting the first two columns (TIME, AM/PM)
    into 24H format. Il campo AM/PM viene preservato nel dizionario finale.
    Vengono anche filtrate le righe che contengono 'Linux' o 'restart'."""
    import re
    parsed_data = []
    header = None

    def is_valid_time(token):
        return re.match(r'^\d{1,2}:\d{2}:\d{2}$', token)

    for line in output.splitlines():
        # Filtra le righe che contengono "Linux" o "restart"
        if re.search(r'\b(Linux|restart)\b', line, flags=re.IGNORECASE):
            continue

        parts = line.split()
        if not parts:
            continue

        # Gestione del flag "Average:"
        if parts[0] == "Average:":
            parts = parts[1:]
            if not average:
                continue

        # Se l'header non è definito, prendi la riga completa se inizia con orario valido
        if header is None:
            if len(parts) >= 2 and is_valid_time(parts[0]) and parts[1] in ["AM", "PM"]:
                header = parts  # conserva l'intero header
            continue

        # Processa le righe dati: controlla se i primi due token sono orario e AM/PM
        if len(parts) >= 2 and is_valid_time(parts[0]) and parts[1] in ["AM", "PM"]:
            converted = convert_to_24h(parts[0], parts[1])
            data_entry = {"date": date_str, "time": converted}
            # Mappa i dati a partire dall'indice 1 del header (per preservare la colonna AM/PM)
            for idx in range(1, min(len(header), len(parts))):
                data_entry[header[idx]] = parts[idx]
            parsed_data.append(data_entry)
        else:
            continue

    return parsed_data

def main():
    """Main execution of the Ansible module."""
    module_args = dict(
        date_start=dict(type="str", required=False, default=None),
        date_end=dict(type="str", required=False, default=None),
        time_start=dict(type="str", required=False, default=None),
        time_end=dict(type="str", required=False, default=None),
        type=dict(type="str", required=True, choices=['cpu', 'memory', 'swap', 'network', 'disk', 'load']),
        average=dict(type="bool", required=False, default=False),
        partition=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    params = module.params
    sar_type = params["type"]
    date_start = params["date_start"]
    date_end = params["date_end"]
    time_start = params["time_start"]
    time_end = params["time_end"]
    average = params["average"]
    partition = params["partition"]

    date_list = []
    if date_start and date_end:
        start_date = datetime.strptime(date_start, "%Y-%m-%d")
        end_date = datetime.strptime(date_end, "%Y-%m-%d")
        delta = (end_date - start_date).days

        if delta < 0:
            module.fail_json(msg="date_end cannot be before date_start.")

        date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(delta + 1)]
    else:
        date_list = [date_start] if date_start else []

    collected_data = []
    for date in date_list:
        sar_file = find_sar_file(date)
        if sar_file:
            collected_data.extend(run_sar_command(module, locate_sar(), sar_file, sar_type, time_start, time_end, partition, average, date))

    fact_name = SAR_FACT_MAPPING.get(sar_type, f"sar_{sar_type}")

    result = {'ansible_facts': {fact_name: collected_data}}

    module.exit_json(**result)


if __name__ == "__main__":
    main()
