<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt">
  <ns prefix="l" uri="http://mccf.artistinprocess.com/lexicon/v2"/>
  <pattern id="unique-ids">
    <rule context="l:Dimension"><assert test="count(../l:Dimension[@id=current()/@id])=1">L01 duplicate Dimension id <value-of select="@id"/></assert></rule>
    <rule context="l:Term"><assert test="count(../l:Term[@id=current()/@id])=1">L02 duplicate Term id <value-of select="@id"/></assert></rule>
  </pattern>
  <pattern id="dimension-shape">
    <rule context="l:Dimension[@type='categorical']">
      <assert test="count(l:Category)&gt;=2">L03 categorical Dimension <value-of select="@id"/> needs at least two Category</assert>
      <assert test="not(l:Level)">L04 categorical Dimension <value-of select="@id"/> must not declare Level</assert>
    </rule>
    <rule context="l:Dimension[@type!='categorical']">
      <assert test="count(l:Level)&gt;=2">L05 Dimension <value-of select="@id"/> needs at least two Level</assert>
      <assert test="not(l:Category)">L06 non-categorical Dimension <value-of select="@id"/> must not declare Category</assert>
    </rule>
  </pattern>
  <pattern id="bipolar-neutral">
    <rule context="l:Dimension[@type='bipolar']">
      <assert test="count(l:Level[@neutral='true'])=1">L07 bipolar Dimension <value-of select="@id"/> needs exactly one neutral Level</assert>
    </rule>
  </pattern>
  <pattern id="unipolar-no-neutral">
    <rule context="l:Dimension[@type='unipolar']">
      <assert test="not(l:Level[@neutral='true'])">L08 unipolar Dimension <value-of select="@id"/> has no neutral point</assert>
    </rule>
  </pattern>
  <pattern id="levels-unique">
    <rule context="l:Level"><assert test="count(../l:Level[@value=current()/@value])=1">L09 duplicate Level value <value-of select="@value"/> in <value-of select="../@id"/></assert></rule>
    <rule context="l:Category"><assert test="count(../l:Category[@id=current()/@id])=1">L10 duplicate Category <value-of select="@id"/></assert></rule>
  </pattern>
  <pattern id="multi-categorical">
    <rule context="l:Dimension[@multi='true']"><assert test="@type='categorical'">L18 multi is for categorical dimensions only (<value-of select="@id"/>)</assert></rule>
  </pattern>
  <pattern id="profile-references">
    <rule context="l:Profile">
      <let name="d" value="/l:Lexicon/l:Dimension[@id=current()/@dimension]"/>
      <assert test="$d">L11 Profile names undeclared dimension <value-of select="@dimension"/></assert>
      <assert test="not($d) or $d/@annotate!='false' or not($d/@annotate)">L12 Profile on non-annotated dimension <value-of select="@dimension"/></assert>
      <assert test="not($d[@type='categorical']) or (@category and not(@level))">L13 categorical dimension needs category, not level (<value-of select="@dimension"/>)</assert>
      <assert test="not($d[@type!='categorical']) or (@level and not(@category))">L14 scaled dimension needs level, not category (<value-of select="@dimension"/>)</assert>
      <assert test="not(@category) or not($d) or $d/l:Category[@id=current()/@category]">L15 undeclared category <value-of select="@category"/></assert>
      <assert test="not(@level) or not($d) or $d/l:Level[@value=current()/@level]">L16 undeclared level <value-of select="@level"/> in <value-of select="@dimension"/></assert>
    </rule>
    <rule context="l:Form"><assert test="/l:Lexicon/l:Term[@id=current()/@term]">L17 Form "<value-of select="@text"/>" points to undeclared term <value-of select="@term"/></assert></rule>
  </pattern>
</schema>
