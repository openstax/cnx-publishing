# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from lxml import etree


class SVGInjectionUtilTestCase(unittest.TestCase):

    @property
    def target(self):
        from ..models import inject_mathml_svgs
        return inject_mathml_svgs

    @mock.patch('cnxpublishing.models.get_current_registry')
    def test_mathml2svg(self, mock_get_current_registry):
        # Mock the registry, since this is a utility test.
        mock_get_current_registry.return_value.settings = {
            'mathml2svg.enabled?': 'on',
            }

        content = """\
<div class="equation">
<math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow> <mi>x</mi> <mo>=</mo> <mfrac> <mrow> <mo>&#8722;<!-- &#8722; --></mo> <mi>b</mi> <mo>&#177;<!-- &#177; --></mo> <msqrt> <msup> <mi>b</mi> <mn>2</mn> </msup> <mo>&#8722;<!-- &#8722; --></mo> <mn>4</mn> <mi>a</mi> <mi>c</mi> </msqrt> </mrow> <mrow> <mn>2</mn> <mi>a</mi> </mrow> </mfrac> </mrow></semantics></math>
</div>"""

        # Mock the external communication with the cnx-mathml2svg service.
        with mock.patch('requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.headers = {'content-type': 'image/svg+xml'}
            post.return_value.text = '<svg>mocked</svg>'
            # Call the target function.
            result = self.target(content)

        elms = etree.fromstring(result)
        annotation = elms.xpath(
            '/div/m:math//m:annotation-xml[@encoding="image/svg+xml"]',
            namespaces={'m': "http://www.w3.org/1998/Math/MathML"})[0]
        expected = """<annotation-xml xmlns="http://www.w3.org/1998/Math/MathML" encoding="image/svg+xml"><svg>mocked</svg></annotation-xml>"""

        self.assertEqual(etree.tostring(annotation), expected)
