<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt">
  <ns prefix="t" uri="http://mccf.artistinprocess.com/trace/v1"/>
  <pattern id="annotation-rules">
    <rule context="t:Annotation">
      <assert test="count(../t:Annotation[@id=current()/@id])=1">A01 duplicate Annotation id <value-of select="@id"/></assert>
      <assert test="starts-with(@annotates,'dialogue:') or starts-with(@annotates,'cue:') or starts-with(@annotates,'episode:')">A02 annotates must be a typed reference</assert>
      <assert test="@annotator!='llm' or (@model and @promptTemplate and @rawRef and @blind!='na')">A03 llm annotation needs model, promptTemplate, rawRef and blind</assert>
      <assert test="@blind!='false' or @ablation">A04 blind=false requires an ablation marker</assert>
      <assert test="@annotator!='lexicon' or @blind='na'">A05 lexicon annotation has blind=na</assert>
      <assert test="@target!='intent' or @annotator='generator' or @annotator='author'">A06 intent comes only from the generator or the author</assert>
      <assert test="@annotator!='generator' or @target='intent'">A07 generator annotates intent only</assert>
      <assert test="@annotator!='lexicon' and @annotator!='llm' or t:Context">A12 lexicon and llm annotations declare their Context</assert>
      <assert test="not(t:Conflict) or t:Dim[@status='conflict']">A13 Conflict without a conflicting Dim</assert>
      <assert test="not(t:Dim[@status='conflict']) or t:Conflict">A14 conflicting Dim without a Conflict record</assert>
    </rule>
    <rule context="t:Conflict">
      <assert test="@resolved='false' or @resolvedBy">A15 a resolved Conflict says who resolved it</assert>
      <assert test="@resolved='true' or not(@resolvedBy)">A16 an unresolved Conflict has no resolvedBy</assert>
    </rule>
    <rule context="t:Dim">
      <assert test="count(../t:Dim[@id=current()/@id])=1">A08 duplicate Dim <value-of select="@id"/> in one annotation</assert>
      <assert test="(@status and not(@level) and not(@category)) or (not(@status) and (@level or @category) and not(@level and @category))">A09 Dim <value-of select="@id"/>: give exactly one of level, category or status</assert>
      <assert test="not(@status) or @status='conflict' or not(t:Evidence)">A10 unknown/notApplicable Dim carries no Evidence</assert>
      <assert test="not(../@annotator='lexicon') or @status='unknown' or @status='notApplicable' or t:Evidence">A11 lexicon Dim <value-of select="@id"/> needs Evidence</assert>
    </rule>
  </pattern>
</schema>
