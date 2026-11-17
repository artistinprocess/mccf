<?xml version="1.0" encoding="UTF-8"?>
<!-- MCCF V5 scene rules (ISO Schematron, XPath 1.0).
     The XSD checks FORM. These rules check MEANING: references that must
     resolve, values that must make sense for this scene's grid.
     Severity: role="error" blocks nothing by default but is reported as an error;
               role="warn"  is reported as a warning. -->
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt">
  <ns prefix="m" uri="http://mccf.artistinprocess.com/v1"/>

  <pattern id="unique-names">
    <rule context="m:Zone">
      <assert role="error" test="count(../m:Zone[@id = current()/@id]) = 1">Duplicate Zone id '<value-of select="@id"/>'.</assert>
      <assert role="error" test="count(../m:Zone[@name = current()/@name]) = 1">Duplicate Zone name '<value-of select="@name"/>'.</assert>
    </rule>
    <rule context="m:Waypoint">
      <assert role="error" test="count(../m:Waypoint[@name = current()/@name]) = 1">Duplicate Waypoint name '<value-of select="@name"/>'.</assert>
    </rule>
    <rule context="m:Line">
      <assert role="error" test="not(@id) or count(../m:Line[@id = current()/@id]) = 1">Duplicate dialogue Line id '<value-of select="@id"/>'.</assert>
    </rule>
    <rule context="m:AgentPlacement">
      <assert role="error" test="count(../m:AgentPlacement[@cultivar = current()/@cultivar]) = 1">Character '<value-of select="@cultivar"/>' is placed more than once.</assert>
    </rule>
  </pattern>

  <pattern id="once-only">
    <rule context="m:Scene">
      <assert role="error" test="count(m:SceneSound) &lt;= 1 and count(m:Zones) &lt;= 1 and count(m:Waypoints) &lt;= 1 and count(m:Paths) &lt;= 1 and count(m:RecordedPaths) &lt;= 1 and count(m:Cameras) &lt;= 1 and count(m:Assets) &lt;= 1 and count(m:EffectTargets) &lt;= 1 and count(m:Navigation) &lt;= 1 and count(m:Background) &lt;= 1 and count(m:Lights) &lt;= 1 and count(m:AudioSources) &lt;= 1 and count(m:MidiSources) &lt;= 1 and count(m:Network) &lt;= 1 and count(m:RouteGraph) &lt;= 1 and count(m:EventCues) &lt;= 1 and count(m:Dialogue) &lt;= 1">A block that may appear only once (Zones, Waypoints, Cameras, Assets, Navigation and so on) appears more than once.</assert>
    </rule>
  </pattern>

  <pattern id="references">
    <rule context="m:Path">
      <assert role="error" test="not(@agent) or @agent = /m:Scene/m:AgentPlacement/@cultivar">Path '<value-of select="@name"/>' belongs to '<value-of select="@agent"/>', who is not placed in this scene.</assert>
    </rule>
    <rule context="m:PathWaypoint">
      <assert role="error" test="@ref = /m:Scene/m:Waypoints/m:Waypoint/@name">Path step '<value-of select="@ref"/>' is not a waypoint in this scene.</assert>
    </rule>
    <rule context="m:Waypoint">
      <assert role="warn" test="not(@zone) or @zone = '' or @zone = /m:Scene/m:Zones/m:Zone/@name or @zone = /m:Scene/m:Zones/m:Zone/@id">Waypoint '<value-of select="@name"/>' names zone '<value-of select="@zone"/>', which does not exist.</assert>
    </rule>
    <rule context="m:Question | m:Response | m:Statement">
      <assert role="warn" test="not(@speaker) or @speaker = /m:Scene/m:AgentPlacement/@cultivar">Speaker '<value-of select="@speaker"/>' is not a character placed in this scene.</assert>
    </rule>
    <rule context="m:Line">
      <assert role="warn" test="not(@actor) or @actor = /m:Scene/m:AgentPlacement/@cultivar">Dialogue line '<value-of select="@id"/>' is spoken by '<value-of select="@actor"/>', who is not placed in this scene.</assert>
    </rule>
    <rule context="m:Cue[@track='gesture' or @track='turn' or @track='path' or @track='behavior']">
      <assert role="warn" test="not(@target) or @target = /m:Scene/m:AgentPlacement/@cultivar">Cue (<value-of select="@track"/>) targets '<value-of select="@target"/>', who is not placed in this scene.</assert>
    </rule>
    <rule context="m:Link">
      <assert role="error" test="@from = /m:Scene/m:AgentPlacement/@cultivar or @from = //m:Zone/@id or substring-after(@from, 'zone:') = //m:Zone/@id">Network link starts at '<value-of select="@from"/>', who is not a placed character or a zone of this scene.</assert>
      <assert role="error" test="@to = /m:Scene/m:AgentPlacement/@cultivar or @to = //m:Zone/@id or substring-after(@to, 'zone:') = //m:Zone/@id">Network link ends at '<value-of select="@to"/>', who is not a placed character or a zone of this scene.</assert>
      <assert role="error" test="@from != @to">Network link from '<value-of select="@from"/>' to itself.</assert>
    </rule>
  </pattern>

  <pattern id="ranges">
    <rule context="m:Zone/m:Weights">
      <assert role="error" test="@E &gt;= 0 and @B &gt;= 0 and @P &gt;= 0 and @S &gt;= 0 and @E &lt;= 1 and @B &lt;= 1 and @P &lt;= 1 and @S &lt;= 1">Zone '<value-of select="../@name"/>' has a weight outside 0 to 1.</assert>
    </rule>
    <rule context="m:Zone/m:Radius">
      <assert role="error" test="@value &gt; 0">Zone '<value-of select="../@name"/>' radius must be greater than 0.</assert>
    </rule>
    <rule context="m:Zone/m:Position">
      <assert role="warn" test="@x &gt;= 0 and @x &lt;= /m:Scene/@width and @z &gt;= 0 and @z &lt;= /m:Scene/@depth">Zone '<value-of select="../@name"/>' is at (<value-of select="@x"/>, <value-of select="@z"/>), outside the <value-of select="/m:Scene/@width"/> x <value-of select="/m:Scene/@depth"/> grid.</assert>
    </rule>
    <rule context="m:StartPosition">
      <assert role="warn" test="@x &gt;= 0 and @x &lt;= /m:Scene/@width and @z &gt;= 0 and @z &lt;= /m:Scene/@depth">'<value-of select="../@cultivar"/>' starts at (<value-of select="@x"/>, <value-of select="@z"/>), outside the <value-of select="/m:Scene/@width"/> x <value-of select="/m:Scene/@depth"/> grid.</assert>
    </rule>
    <rule context="m:Waypoint">
      <assert role="warn" test="@pos_x &gt;= 0 and @pos_x &lt;= /m:Scene/@width and @pos_z &gt;= 0 and @pos_z &lt;= /m:Scene/@depth">Waypoint '<value-of select="@name"/>' is at (<value-of select="@pos_x"/>, <value-of select="@pos_z"/>), outside the grid.</assert>
      <assert role="error" test="not(@dwell) or @dwell &gt;= 0">Waypoint '<value-of select="@name"/>' has a negative dwell.</assert>
      <assert role="error" test="not(@pace) or @pace &gt; 0">Waypoint '<value-of select="@name"/>' pace must be greater than 0.</assert>
    </rule>
    <rule context="m:Cue">
      <assert role="error" test="not(@t0) or @t0 &gt;= 0">Cue (<value-of select="@track"/>) starts at a negative time.</assert>
    </rule>
    <rule context="m:Link">
      <assert role="warn" test="not(@strength) or (@strength &gt;= 0 and @strength &lt;= 1)">Network link <value-of select="@from"/> to <value-of select="@to"/> has strength outside 0 to 1.</assert>
    </rule>
  </pattern>
</schema>
