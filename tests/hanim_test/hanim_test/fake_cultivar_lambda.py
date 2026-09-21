"""Stand-in for mccf_cultivar_lambda.CultivarDefinition (real module not uploaded).
Only implements what hanim_export touches: from_xml / to_xml / hanim_src / receptivity /
behavior_clips / behavior_default. Clips round-trip as JSON inside a <Behaviors> element."""
import json
import xml.etree.ElementTree as ET

class CultivarDefinition:
    def __init__(self):
        self.name = ''
        self.hanim_src = ''
        self.receptivity = {}
        self.behavior_clips = []
        self.behavior_default = ''

    @classmethod
    def from_xml(cls, text):
        root = ET.fromstring(text)
        c = cls()
        c.name = root.get('name', '')
        c.hanim_src = root.get('hanim_src', '')
        b = root.find('Behaviors')
        if b is not None and b.text:
            c.behavior_clips = json.loads(b.text)
        c.behavior_default = root.get('behavior_default', '')
        return c

    def to_xml(self):
        root = ET.Element('Cultivar', name=self.name, hanim_src=self.hanim_src,
                          behavior_default=self.behavior_default)
        b = ET.SubElement(root, 'Behaviors')
        b.text = json.dumps(self.behavior_clips)
        return ET.tostring(root, encoding='unicode')
