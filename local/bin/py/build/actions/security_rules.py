#!/usr/bin/env python3
import glob
import json
import os
import re
from itertools import chain

import yaml
import logging
from pathlib import Path
from jinja2 import Environment, Template, select_autoescape, Undefined
from jinja2.loaders import DictLoader

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

TEMPLATE = """\
---
{front_matter}
---

{content}
"""


class SilentUndefined(Undefined):
    def _fail_with_undefined_error(self, *args, **kwargs):
        return None

nop = lambda *a, **k: None

def load_templated_file(f):
    # read without the import first line
    f.seek(0)
    content_without_import = ''.join(f.readlines()[1:])
    env = Environment(
        undefined=SilentUndefined,
        loader=DictLoader(dict()),
        autoescape=select_autoescape(),
        variable_start_string="{@",
        variable_end_string="@}"
    )
    template = env.from_string(content_without_import)
    data = yaml.safe_load(template.render(fim={'watch_files': nop}))
    return data

def update_global_aliases(index_path, global_aliases):
    content = ''
    new_yml = {}
    boundary = re.compile(r'^-{3,}$', re.MULTILINE)
    with open(index_path, 'r') as f:
        content = f.read()
    split = boundary.split(content, 2)
    _, fm, content = split
    new_yml = yaml.load(fm, Loader=yaml.FullLoader)
    fm_aliases = list(set(new_yml.get("aliases", []) + global_aliases))
    new_yml['aliases'] = fm_aliases
    with open(index_path, mode='w', encoding='utf-8') as out_file:
        output_content = TEMPLATE.format(front_matter=yaml.dump(new_yml, default_flow_style=False).strip(),
                        content=content.strip())
        out_file.write(output_content)

def security_rules(content, content_dir):
    """
    Takes the content from a file from a github repo and
    pushed it to the doc
    See https://github.com/DataDog/documentation/wiki/Documentation-Build#pull-and-push-files to learn more
    :param content: object with a file_name, a file_path, and options to apply
    :param content_dir: The directory where content should be put
    """
    logger.info("Starting security rules action...")
    global_aliases = []
    for file_name in chain.from_iterable(glob.glob(pattern, recursive=True) for pattern in content["globs"]):

        data = None
        if file_name.endswith(".json"):
            with open(file_name, mode="r+") as f:
                try:
                    data = json.loads(f.read())
                except:
                    logger.warn(f"Error parsing {file_name}")
        elif file_name.endswith(".yaml"):
            with open(file_name, mode="r+") as f:
                try:
                    file_text_content = f.read()
                    if 'jinja2' in file_text_content:
                        data = load_templated_file(f)
                    else:
                        data = yaml.load(file_text_content, Loader=yaml.FullLoader)
                except:
                    logger.warn(f"Error parsing {file_name}")

        p = Path(f.name)
        message_file_name = p.with_suffix('.md')

        if data and message_file_name.exists():
            # delete file or skip if staged
            # any() will return True when at least one of the elements is Truthy
            if 'restrictedToOrgs' in data or data.get('isStaged', False) or data.get('isDeleted', False) or not data.get('isEnabled', True):
                if p.exists():
                    logger.info(f"removing file {p.name}")
                    global_aliases.append(f"/security_monitoring/default_rules/{p.stem}")
                    global_aliases.append(f"/security_platform/default_rules/{p.stem}")
                    p.unlink()
                else:
                    logger.info(f"skipping file {p.name}")
            else:
                # The message of a detection rule is located in a Markdown file next to the rule definition
                with open(str(message_file_name), mode="r+") as message_file:
                    message = message_file.read()

                    # strip out [text] e.g "[CIS Docker] Ensure that.." becomes "Ensure that..."
                    parsed_title = re.sub(r"\[.+\]\s?(.*)", "\\1", data.get('name', ''), 0, re.MULTILINE)
                    page_data = {
                        "title": parsed_title,
                        "kind": "documentation",
                        "type": "security_rules",
                        "disable_edit": True,
                        "aliases": [
                            f"{data.get('defaultRuleId', '').strip()}",
                            f"/security_monitoring/default_rules/{data.get('defaultRuleId', '').strip()}",
                            f"/security_monitoring/default_rules/{p.stem}"
                        ],
                        "rule_category": [],
                        "integration_id": ""
                    }

                    # we need to get the path relative to the repo root for comparisons
                    extract_dir, relative_path = str(p.parent).split(f"/{content['repo_name']}/")
                    # lets build up this categorization for filtering purposes
                    if 'configuration' in relative_path:
                        page_data['rule_category'].append('Cloud Configuration')
                    if 'security-monitoring' in relative_path:
                        page_data['rule_category'].append('Log Detection')
                    if 'runtime' in relative_path:
                        if 'compliance' in relative_path:
                            page_data['rule_category'].append('Infrastructure Configuration')
                        else:
                            page_data['rule_category'].append('Workload Security')

                    tags = data.get('tags', [])
                    if tags:
                        if data.get('source', ''):
                            page_data["source"] = data.get('source', '')
                        for tag in tags:
                            if ':' in tag:
                                key, value = tag.split(':')
                                page_data[key] = value
                    else:
                        # try build up manually
                        if content['action'] == 'compliance-rules':
                            source = data.get('source', None)
                            tech = data.get('framework', {}).get('name', '').replace('cis-', '')
                            page_data["source"] = source or tech
                            page_data["security"] = "compliance"
                            page_data["framework"] = data.get('framework', {}).get('name', '')
                            page_data["control"] = data.get('control', '')
                            page_data["scope"] = tech

                    # lowercase them
                    if page_data.get("source", None):
                        page_data["source"] = page_data["source"].lower()
                    if page_data.get("scope", None):
                        page_data["scope"] = page_data["scope"].lower()

                    # integration id
                    page_data["integration_id"] = page_data.get("scope", None) or page_data.get("source", "")
                    cloud = page_data.get("cloud", None)
                    if cloud and cloud == 'aws':
                        page_data["integration_id"] = "amazon-{}".format(page_data["integration_id"])

                    front_matter = yaml.dump(page_data, default_flow_style=False).strip()
                    output_content = TEMPLATE.format(front_matter=front_matter, content=message.strip())

                    dest_dir = Path(f"{content_dir}{content['options']['dest_path']}")
                    dest_dir.mkdir(exist_ok=True)
                    dest_file = dest_dir.joinpath(p.name).with_suffix('.md')
                    logger.info(dest_file)
                    with open(dest_file, mode='w', encoding='utf-8') as out_file:
                        out_file.write(output_content)

    # add global aliases from deleted files to _index.md
    if os.environ.get('CI_ENVIRONMENT_NAME', '') in ('live', 'preview'):
        index_path = Path(f"{content_dir}{content['options']['dest_path']}_index.md")
        update_global_aliases(index_path, global_aliases)


def compliance_rules(content, content_dir):
    """
    Takes the content from a file from a github repo and
    pushed it to the doc
    See https://github.com/DataDog/documentation/wiki/Documentation-Build#pull-and-push-files to learn more
    :param content: object with a file_name, a file_path, and options to apply
    :param content_dir: The directory where content should be put
    """
    global_aliases = []
    logger.info("Starting compliance rules action...")
    for file_name in chain.from_iterable(glob.glob(pattern, recursive=True) for pattern in content["globs"]):
        # Only loop over rules JSON files (not eg. Markdown files containing the messages)
        if not file_name.endswith(".json"):
            continue
        with open(file_name, mode="r+") as f:
            try:
                json_data = json.loads(f.read())
            except:
                logger.warn(f"Error parsing {file_name}")
            p = Path(f.name)

            # delete file or skip if staged
            if 'restrictedToOrgs' in json_data or json_data.get('isStaged', False) or json_data.get('isDeleted', False) or not json_data.get('enabled', True):
                if p.exists():
                    logger.info(f"removing file {p.name}")
                    global_aliases.append(f"/security_monitoring/default_rules/{p.stem}")
                    global_aliases.append(f"/security_platform/default_rules/{p.stem}")
                    p.unlink()
                else:
                    logger.info(f"skipping file {p.name}")
            else:
                # The message of a detection rule is located in a Markdown file next to the rule definition
                message_file_name = file_name.rsplit(".", 1)[0] + ".md"

                with open(message_file_name, mode="r+") as message_file:
                    message = message_file.read()

                    parsed_title = re.sub(r"\[.+\]\s?(.*)", "\\1", json_data.get('name', ''), 0, re.MULTILINE)
                    page_data = {
                        "title": f"{parsed_title}",
                        "kind": "documentation",
                        "type": "security_rules",
                        "disable_edit": True,
                        "aliases": [f"{json_data.get('defaultRuleId', '').strip()}"],
                        "source": f"{json_data.get('framework', {}).get('name', '').replace('cis-','')}",
                        "integration_id": ""
                    }

                    for tag in json_data.get('tags', []):
                        key, value = tag.split(':')
                        page_data[key] = value

                    # lowercase them
                    if page_data.get("source", None):
                        page_data["source"] = page_data["source"].lower()
                    if page_data.get("scope", None):
                        page_data["scope"] = page_data["scope"].lower()

                    # integration id
                    page_data["integration_id"] = page_data.get("scope", None) or page_data.get("source", "")
                    cloud = page_data.get("cloud", None)
                    if cloud and cloud == 'aws':
                        page_data["integration_id"] = "amazon-{}".format(page_data["integration_id"])

                    front_matter = yaml.dump(page_data, default_flow_style=False).strip()
                    output_content = TEMPLATE.format(front_matter=front_matter, content=message.strip())

                    dest_dir = Path(f"{content_dir}{content['options']['dest_path']}")
                    dest_dir.mkdir(exist_ok=True)
                    dest_file = dest_dir.joinpath(p.name).with_suffix('.md')
                    logger.info(dest_file)
                    with open(dest_file, mode='w', encoding='utf-8') as out_file:
                        out_file.write(output_content)

    # add global aliases from deleted files to _index.md
    if os.environ.get('CI_ENVIRONMENT_NAME', '') in ('live', 'preview'):
        index_path = Path(f"{content_dir}{content['options']['dest_path']}_index.md")
        update_global_aliases(index_path, global_aliases)
