from src.application.parser.siq_parser import SiqParser

def test_siq_parser_xml():
    xml_data = b"""<?xml version="1.0" encoding="utf-8"?>
    <package name="Test Package" version="4" xmlns="http://vladimirkhil.com/ygpackage3.0.xsd">
      <info>
        <authors>
          <author>Author Name</author>
        </authors>
      </info>
      <rounds>
        <round name="Round 1">
          <themes>
            <theme name="Theme 1">
              <questions>
                <question price="100">
                  <scenario>
                     <atom type="text">What's the meaning of life?</atom>
                  </scenario>
                  <right>
                     <answer>42</answer>
                  </right>
                </question>
                <question price="200">
                  <scenario>
                     <atom type="image">@image.jpg</atom>
                  </scenario>
                  <right>
                     <answer>A picture</answer>
                  </right>
                </question>
              </questions>
            </theme>
          </themes>
        </round>
      </rounds>
    </package>
    """
    
    from unittest.mock import MagicMock
    import zipfile
    
    parser = SiqParser()
    mock_zf = MagicMock(spec=zipfile.ZipFile)
    mock_zf.namelist.return_value = []
    
    package = parser._parse_xml(xml_data, mock_zf, [])
    
    assert package.title == "Test Package"
    assert package.author == "Author Name"
    assert len(package.rounds) == 1
    
    round1 = package.rounds[0]
    assert round1.name == "Round 1"
    assert not round1.is_final
    assert len(round1.themes) == 1
    
    theme1 = round1.themes[0]
    assert theme1.name == "Theme 1"
    assert len(theme1.questions) == 2
    
    q1 = theme1.questions[0]
    assert q1.value == 100
    assert "What's the meaning of life?" in q1.text
    assert q1.answer == "42"
    
    q2 = theme1.questions[1]
    assert q2.value == 200
    assert "[Пустой вопрос]" in q2.text
    assert q2.answer == "A picture"

