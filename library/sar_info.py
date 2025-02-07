#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright: (c) 2025 Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import annotations


DOCUMENTATION = r"""
---
module: sar_info
short_description: Collect system activity report (SAR) data for system performance monitoring.
description:
  - Retrieves SAR data using the `sar` command from system logs.
  - Supports filtering by date range, time range, and partition details.
  - Returns performance metrics such as cpu utilization, memory usage, disk activity, and network statistics.
options:
  date_start:
    description: Start date for collecting SAR data (format DD/MM/YYYY).
    required: false
    type: str
  date_end:
    description: End date for collecting SAR data (format DD/MM/YYYY).
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
"""

EXAMPLES = r"""
- name: Collect disk data for all partitions from 06/02/2025 to 07/02/2025
  sar_info:
    type: "disk"
    date_start: "06/02/2025"
    date_end: "07/02/2025"
    partition: true
  register: sar_output

- name: Get all await values for centos-root device
  set_fact:
    await_values: "{{ ansible_facts.sar_data.disk | selectattr('DEV', 'equalto', 'centos-root') | map(attribute='await') | list }}"

- name: Get cpu data between 08:00:00 and 12:00:00 for all stored days
  sar_info:
    type: "cpu"
    time_start: "08:00:00"
    time_end: "12:00:00"

- name: Fetch memory usage data for 07/02/2025
  sar_info:
    type: "memory"
    date_start: "07/02/2025"

- name: Get only average disk data for 06/02/2025
  sar_info:
    type: "disk"
    date_start: "06/02/2025"
    average: true

- name: Retrieve system load average for today
  sar_info:
    type: "load"

"""

RETURN = r"""
ansible_facts:
  description: "SAR data collected from system logs."
  returned: always
  type: complex
  contains:
    sar_data:
      description: extracted sar data
      returned: always
      type: list
      elements: dict
      sample:
        sar_data:
          disk:
            - date: "06/02/2025"
              time: "05:40:01"
              DEV: "centos-root"
              await: "2.13"
            - date: "06/02/2025"
              time: "05:50:01"
              DEV: "centos-root"
              await: "1.50"

"""

from ansible.module_utils.basic import AnsibleModule
import os
import subprocess
import datetime

SAR_LOG_PATHS = ["/var/log/sa/", "/var/log/sysstat/"]
SAR_BIN_PATHS = ["/usr/bin/sar", "/usr/sbin/sar", "/bin/sar"]


def locate_sar():
    for path in SAR_BIN_PATHS:
        if os.path.exists(path):
            return path
    return None


def find_sar_file(date_str):
    try:
        date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
        day = date_obj.strftime("%d")

        for path in SAR_LOG_PATHS:
            file_path = os.path.join(path, f"sa{day}")
            if os.path.exists(file_path):
                return file_path

    except ValueError:
        return None

    return None


def run_sar_command(module, sar_bin, sar_file, sar_type, time_start, time_end, partition, average, date_str):
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


def parse_sar_output(output, sar_type, average, date_str):
    sar_data = []
    lines = output.splitlines()
    headers = None
    collect_avg = average

    for line in lines:
        parts = line.split()
        if not parts:
            continue

        if sar_type == "cpu" and ("%user" in parts or "%usr" in parts):
            headers = parts
            continue
        elif sar_type == "memory" and ("kbmemfree" in parts or "kbmemused" in parts):
            headers = parts
            continue
        elif sar_type == "swap" and ("kbswpfree" in parts or "kbswpused" in parts):
            headers = parts
            continue
        elif sar_type == "network" and ("IFACE" in parts or "rxpck/s" in parts):
            headers = parts
            continue
        elif sar_type == "disk" and ("DEV" in parts or "tps" in parts):
            headers = parts
            continue
        elif sar_type == "load" and ("runq-sz" in parts or "plist-sz" in parts):
            headers = parts
            continue

        if headers is None:
            continue

        is_avg = parts[0] == "Average:"

        if collect_avg and not is_avg:
            continue
        elif not collect_avg and is_avg:
            continue

        time_str = parts[0] if not is_avg else "Average"

        data_entry = {
            "date": date_str,
            "time": time_str
        }

        for i, key in enumerate(headers[1:], start=1):
            if i < len(parts):
                data_entry[key] = parts[i]

        sar_data.append(data_entry)

    return sar_data


def main():
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

    sar_data = []

    for date in [date_start, date_end] if date_start == date_end else [
        (datetime.datetime.strptime(date_start, "%d/%m/%Y") + datetime.timedelta(days=i)).strftime("%d/%m/%Y")
        for i in range((datetime.datetime.strptime(date_end, "%d/%m/%Y") - datetime.datetime.strptime(date_start, "%d/%m/%Y")).days + 1)
    ]:
        sar_file = find_sar_file(date)
        if sar_file:
            sar_data.extend(run_sar_command(module, locate_sar(), sar_file, sar_type, time_start, time_end, partition, average, date))

    module.exit_json(changed=False, ansible_facts={"sar_data": {sar_type: sar_data}})


if __name__ == "__main__":
    main()
