"""Ensures that technology and fuel names match the convention

For example, to validate the following list of names, you would use the
config shown below::

    theseUNIQUE_ENTRY1
    are__UNIQUE_ENTRY2
    all__UNIQUE_ENTRY1
    validUNIQUE_ENTRY2
    entryUNIQUE_ENTRY1
    in__UNIQUE_ENTRY2
    a____UNIQUE_ENTRY1
    list_UNIQUE_ENTRY2

Create a yaml validation config with the following format::

    codes:
      some_valid_codes:
        UNIQUE_ENTRY1: Description of unique entry 1
        UNIQUE_ENTRY2: Description of unique entry 2
    schema:
      schema_name:
      - name: first_entry_in_schema
        valid: ['these', 'are__', 'all__', 'valid', 'entry', 'in__', 'a____', 'list_']
        position: (1, 5) # a tuple representing the start and end position
      - name: second_entry_in_schema
        valid: some_valid_codes  # references an entry in the codes section of the config
        position: (6, 19) # a tuple representing the start and end position

"""

import logging
import re
from collections import defaultdict
from typing import Dict, List

import networkx.algorithms.isolate as isolate

from otoole import read_datapackage, read_packaged_file
from otoole.visualise.res import create_graph

logger = logging.getLogger(__name__)


def read_validation_config():
    return read_packaged_file('validate.yaml', 'otoole')


def check_for_duplicates(codes: List) -> bool:
    duplicate_values = len(codes) != len(set(codes))
    return duplicate_values


def create_schema(config: Dict = None):
    """Populate the dict of schema with codes from the validation config

    Arguments
    ---------
    config : dict, default=None
        A configuration dictionary containing ``codes`` and ``schema`` keys
    """
    if config is None:
        config = read_validation_config()

    for _, schema in config['schema'].items():
        for name in schema:
            if isinstance(name['valid'], str):
                name['valid'] = list(config['codes'][name['valid']].keys())
                logger.debug("create_schema: %s", name['valid'])
            elif isinstance(name['valid'], list):
                pass
            else:
                raise ValueError("Entry {} is not correct".format(name['name']))
            if check_for_duplicates(name['valid']):
                raise ValueError("There are duplicate values in codes for {}", name['name'])
    return config['schema']


def compose_expression(schema: List) -> str:
    """Generates a regular expression from a schema

    Returns
    -------
    str
    """
    expression = "^"
    for x in schema:
        logger.debug("compose_expression: %s", x['valid'])
        valid_entries = "|".join(x['valid'])
        expression += "({})".format(valid_entries)
    return expression


def validate(expression: str, name: str) -> bool:
    """Determine if ``name`` matches the ``expression``

    Arguments
    ---------
    expression : str
    name : str

    Returns
    -------
    bool
    """
    logger.debug("Running validation for %s", name)

    valid = False

    pattern = re.compile(expression)

    if pattern.fullmatch(name):
        valid = True
    else:
        valid = False
    return valid


def validate_resource(package, schema, resource):

    logger.debug(schema)

    expression = compose_expression(schema)
    resources = package.get_resource(resource).read(keyed=True)

    valid_names = []
    invalid_names = []

    for row in resources:
        name = row['VALUE']
        valid = validate(expression, row['VALUE'])
        if valid:
            valid_names.append(name)
        else:
            invalid_names.append(name)

    if invalid_names:
        msg = "{} invalid names:\n    {}"
        print(msg.format(len(invalid_names), ", ".join(invalid_names)))
    if valid_names:
        msg = "{} valid names:\n    {}"
        print(msg.format(len(valid_names), ", ".join(valid_names)))


def identify_orphaned_fuels_techs(package) -> Dict[str, str]:
    """Returns a list of fuels and technologies which are unconnected

    Returns
    -------
    dict

    """
    graph = create_graph(package)

    number_of_isolates = isolate.number_of_isolates(graph)
    logger.debug("There are {} isolated nodes in the graph".format(number_of_isolates))

    isolated_nodes = defaultdict(list)

    for node_name in list(isolate.isolates(graph)):
        node_data = graph.nodes[node_name]
        isolated_nodes[node_data['type']].append(node_name)

    return isolated_nodes


def main(file_format: str, filepath: str, config=None):

    print("\n***Beginning validation***")
    if file_format == 'datapackage':
        package = read_datapackage(filepath)
    elif file_format == 'sql':
        package = read_datapackage(filepath, sql=True)

    schema = create_schema(config)

    print("\n***Checking TECHNOLOGY names***\n")
    validate_resource(package, schema['technology_name'], 'TECHNOLOGY')

    print("\n***Checking FUEL names***\n")
    validate_resource(package, schema['fuel_name'], 'FUEL')

    print("\n***Checking graph structure***")
    isolated_nodes = identify_orphaned_fuels_techs(package)
    msg = ""
    for node_type, node_names in isolated_nodes.items():
        msg += "\n{} '{}' nodes are isolated:\n     {}\n".format(
            len(node_names), node_type, ", ".join(node_names))
    print(msg)
