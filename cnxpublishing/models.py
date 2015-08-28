# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import requests
from lxml import etree
from pyramid.settings import asbool
from pyramid.threadlocal import get_current_registry


MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"
NSMAP = {'m': MATHML_NAMESPACE}


def _find_or_create_semantics_block(math_block):
    """Finds or creates the MathML semantics tag."""
    try:
        semantics_block = math_block.xpath(
            '/m:samantics',
            namespaces=NSMAP)[0]
    except IndexError:
        # Move all the contents of the math_block into a semantics wrapper.
        children = []
        for child in math_block.getchildren():
            children.append(child)
            math_block.remove(child)  # why no pop?
        semantics_block = etree.SubElement(
            math_block,
            '{{{}}}semantics'.format(MATHML_NAMESPACE))
        for child in children:
            semantics_block.append(child)
    return semantics_block


def inject_mathml_svgs(content):
    """Inject MathML SVG annotations into HTML content."""
    settings = get_current_registry().settings
    is_enabled = asbool(settings.get('mathml2svg.enabled?', False))
    url = settings.get('mathml2svg.url')

    # Bailout when svg generation is disabled.
    if not is_enabled:
        return content

    xml = etree.fromstring(content)
    math_blocks = xml.xpath(
        '//m:math[not(/m:annotation-xml[@encoding="image/svg+xml"])]',
        namespaces=NSMAP)
    for math_block in math_blocks:
        # Submit the MathML block to the SVG generation service.
        payload = {'MathML': etree.tostring(math_block)}
        response = requests.post(url, data=payload)
        # Inject the SVG into the MathML as an annotation
        # only if the resposne was good, otherwise skip over it.
        if response.status_code == 200:
            semantics_wrapper = _find_or_create_semantics_block(math_block)
            svg = response.text
            content_type = response.headers['content-type']
            # Insert the svg into the content
            annotation = etree.SubElement(
                semantics_wrapper,
                '{{{}}}annotation-xml'.format(MATHML_NAMESPACE))
            annotation.set('encoding', content_type)
            annotation.append(etree.fromstring(svg))
    modified_content = etree.tostring(xml)
    return modified_content
