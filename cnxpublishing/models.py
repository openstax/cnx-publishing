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


def inject_mathml_svgs(content):
    """Inject MathML SVG annotations into HTML content."""
    settings = get_current_registry().settings
    is_enabled = asbool(settings.get('mathml2svg.enabled?', False))
    url = settings.get('mathml2svg.url')

    # Bailout when svg generation is disabled.
    if not is_enabled:
        return content

    xml = etree.fromstring(content)
    mathml_namespace = "http://www.w3.org/1998/Math/MathML"
    mathml_blocks = xml.xpath(
        '//m:math[not(/m:annotation-xml[@encoding="image/svg+xml"])]',
        namespaces={'m': mathml_namespace})
    for mathml_block in mathml_blocks:
        # Submit the MathML block to the SVG generation service.
        payload = {'MathML': etree.tostring(mathml_block)}
        response = requests.post(url, data=payload)
        # Inject the SVG into the MathML as an annotation
        # only if the resposne was good, otherwise skip over it.
        semantic_block = mathml_block.getchildren()[0]
        if response.status_code == 200:
            svg = response.text
            content_type = response.headers['content-type']
            # Insert the svg into the content
            annotation = etree.SubElement(
                semantic_block,
                '{{{}}}annotation-xml'.format(mathml_namespace))
            annotation.set('encoding', content_type)
            annotation.append(etree.fromstring(svg))
    modified_content = etree.tostring(xml)
    return modified_content
