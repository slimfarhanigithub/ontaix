## Abstract

The PROV Ontology (PROV-O) expresses the PROV Data Model [] using the OWL2 Web Ontology Language (OWL2) []. It provides a set of classes, properties, and restrictions that can be used to represent and interchange provenance information generated in different systems and under different contexts. It can also be specialized to create new classes and properties to model provenance information for different applications and domains. The PROV Document Overview describes the overall state of PROV, and should be read before other PROV documents.
The namespace for all PROV-O terms is
The OWL encoding of the PROV Ontology is available here.

## 1. Introduction

The PROV Ontology (PROV-O) defines the OWL2 Web Ontology Language encoding of the PROV Data Model []. This document describes the set of classes, properties, and restrictions that constitute the PROV Ontology. This ontology specification provides the foundation to implement provenance applications in different domains that can represent, exchange, and integrate provenance information generated in different systems and under different contexts. Together with the PROV Access and Query [] and PROV Data Model [], this document forms a framework for provenance information interchange in domain-specific Web-based applications.
PROV-O is a lightweight ontology that can be adopted in a wide range of applications. With the exception of five axioms, PROV-O conforms to the OWL-RL profile []. The PROV Ontology classes and properties are defined such that they can not only be used directly to represent provenance information, but also can be specialized for modeling application-specific provenance details in a variety of domains. Thus, the PROV Ontology is expected to be both directly usable in applications as well as serve as a reference model for creating domain-specific provenance ontologies and thereby facilitates interoperable provenance modeling. To demonstrate the use of PROV-O classes and properties, this document uses an example provenance scenario similar to the one introduced in the PROV-Primer [].
The PROV Data Model [] introduces a set of concepts to represent provenance information in a variety of application domains. This document maps the PROV Data Model to PROV Ontology using the OWL2 ontology language [].
We briefly introduce some of the OWL2 modeling terms that will be used to describe the PROV Ontology. An OWL2 instance is an individual object in a domain of discourse, for example a person named Alice or a car named KITT. A set of individuals sharing common characteristics constitutes a class. Person and Car are examples of classes representing the set of individual persons and cars respectively. The OWL2 object properties are used to link individuals, classes, or create a property hierarchy. For example, the object property "hasOwner" can be used to link car with person. The OWL2 datatype properties are used to link individuals or classes to data values, including XML Schema datatypes [].

### 1.1 Compliance with this Document

For the purpose of compliance, the normative sections of this document are Section 1.1, Section 1.2, Section 3, Section 4, and Appendix B
- Information in tables is normative if it appears in a normative section.
- All figures and diagrams are informative.
- All examples are informative.

### 1.2 Notational Conventions

The key words "must", "must not", "required", "shall", "shall not", "should", "should not", "recommended", "may", and "optional" in this document are to be interpreted as described in [].

### 1.3 Namespaces

This section is non-normative.
The following namespace prefixes are used throughout this document.
Table 1: Prefix and Namespaces used in this specification
prefix
namespace IRI
definition
rdf
The RDF namespace []
xsd
XML Schema Namespace []
owl
The OWL namespace []
prov
The PROV namespace []
(others)
(various)
All other namespace prefixes are used in examples only.
In particular, IRIs starting with " represent
some application-dependent IRI []

## 2. PROV-O at a glance

This section is non-normative.
PROV-O users may only need to use parts of the entire ontology, depending on their needs and according to how much detail they want to include in their provenance information. For this, the PROV-O terms (classes and properties) are grouped into three categories to provide an incremental introduction to the ontology: Starting Point terms, Expanded terms, and terms for Qualifying relationships.
Starting Point classes and properties provide the basis for the rest of the PROV Ontology and thus it is recommended that readers become comfortable with how to apply these terms before continuing to the remaining categories. These terms are used to create simple provenance descriptions that can be elaborated using terms from other categories. The classes and properties in this category are listed below and are discussed in Section 3.1.
Expanded classes and properties provide additional terms that can be used to relate classes in the Starting Point category. The terms in this category are applied in the same way as the terms in the Starting Point category. Many of the terms in this category are subclasses or subproperties of those in the Starting Point category. The classes and properties in this category are listed below and are discussed in Section 3.2.
Qualified classes and properties provide elaborated information about binary relations asserted using Starting Point and Expanded properties. The terms in this category are applied using a pattern that differs from those in the Starting Point and Expanded categories. While the relations from the previous two categories are applied as direct, binary assertions, the terms in this category are used to provide additional attributes of the binary relations. The pattern used in this category allows users to provide elaborate details that are not available using only Starting Point and Expanded terms. The classes and properties in this category are listed below and are discussed in Section 3.3.

## 3. The PROV-O Ontology Description

This section introduces the terms in each of the following categories:
- Starting Point Terms
- Expanded Terms
- Qualified Terms

### 3.1 Starting Point Terms

The Starting Point category is a small set of classes and properties that can be used to create simple, initial provenance descriptions. Three classes provide a basis for the rest of PROV-O:
- An prov:Entity is a physical, digital, conceptual, or other kind of thing with some fixed aspects; entities may be real or imaginary.
- An prov:Activity is something that occurs over a period of time and acts upon or with entities; it may include consuming, processing, transforming, modifying, relocating, using, or generating entities.
- An prov:Agent is something that bears some form of responsibility for an activity taking place, for the existence of an entity, or for another agent's activity.
The three primary classes relate to one another and to themselves using the properties shown in the following figure.
Activities start and end at particular points in time (described using properties prov:startedAtTime and prov:endedAtTime, respectively) and during their lifespan can use and generate a variety of Entities (described with prov:used and prov:wasGeneratedBy, respectively). For example, a blog writing activity may use a particular dataset and generate a bar chart. By expressing usage and generation, one can construct provenance chains comprising both Activities and Entities.
In addition, we can say that an Activity prov:wasInformedBy another Activity to provide some dependency information without explicitly providing the activities' start and end times. A prov:wasInformedBy relation between Activities suggests that the informed Activity used an Entity that was generated by the informing Activity, but the Entity itself is unknown or is not of interest. So, the prov:wasInformedBy property allows the construction of provenance chains comprising only Activities.
Provenance chains comprising only Entities can be formed using the prov:wasDerivedFrom property. A derivation is a transformation of one entity into another. For example, if the Activity that created the bar chart is not known or is not of interest, then we can say that the bar chart prov:wasDerivedFrom the dataset. Arbitrary RDF properties can be used to describe the fixed aspects of an Entity that are interesting within a particular application (for example, the file size and format of the dataset, or the aspect ratio of the bar chart).
While the properties prov:used, prov:wasGeneratedBy, prov:wasInformedBy, and prov:wasDerivedFrom can be used to construct provenance chains among Activities and Entities, Agents may also be ascribed responsibility for any Activity or Entity within a provenance chain. An Agent's responsibility for an Activity or Entity is described using the properties prov:wasAssociatedWith and prov:wasAttributedTo, respectively. Agents can also be responsible for other Agents' actions. In this case of delegation, the influencing Agent prov:actedOnBehalfOf another Agent that also bears responsibility for the influenced Activity or Entity.
The properties rdf:type and rdfs:label are used to express prov:type and prov:label, respectively.
Figure 1. The three Starting Point classes and the properties that relate them.
The diagrams in this document depict Entities as yellow ovals,
Activities as blue rectangles, and Agents as orange pentagons.
The responsibility properties are shown in pink.
Example 1: The following PROV-O describes the resources involved when creating a chart about crime statistics. The example uses only Starting Point terms and serves as a basis for elaboration that will be described in subsequent sections. In the example, Derek performs an aggregation of some government crime data, grouping by national regions that are described in a separate dataset by a civil action group.
The example states that the agent :derek was associated with two activities: :aggregationActivity and :illustrationActivity. The activity :aggregationActivity used the entities :crimeData (a crime statistics dataset) and :nationalRegionsList (a list of national regions), and generated a new entity, :aggregatedByRegions that aggregates the statistics in :crimeData according to the regions in :nationalRegionsList. The :aggregatedByRegions entity was then used by the :illustrationActivity activity, to generate a new entity :bar_chart that depicts the aggregated statistics.
The example also states that the activity :illustrationActivity was informed by the activity :aggregationActivity. Indeed, the former used the entity :aggregatedByRegions, which was generated by the latter.
Because the agent :derek was associated with the activities :aggregationActivity and :illustrationActivity, the entities generated by these activities, i.e., :aggregatedByRegions and :bar_chart, were also attributed to him.
Finally, the example states that the agent :derek acted on behalf of the organization :national_newspaper_inc.
Figure 2. A graphical illustration of the PROV-O in Example 1, showing how the three Starting Point classes relate.
The diagrams in this document depict Entities as yellow ovals, Activities as blue rectangles,
and Agents as orange pentagons. The responsibility properties are shown in pink.

### 3.2 Expanded Terms

The terms introduced in this section provide additional ways to describe the provenance among Entities, Activities, and Agents. The additional terms are illustrated in the following figure and can be separated into five different categories.
Figure 3. The expanded terms build upon those in the Starting Points section.
The diagrams in this document depict Entities as yellow ovals, Activities as blue rectangles, and Agents as orange pentagons.
The domain of prov:atLocation (prov:Activity or prov:Entity or prov:Agent or prov:InstantaneousEvent) is not illustrated.
The first category extends the Starting Point terms with subclasses, subproperties, and a superproperty.
Three subclasses of Agent (prov:Person, prov:Organization, and prov:SoftwareAgent) and three subclasses of Entity are provided (prov:Collection, prov:Bundle, and prov:Plan).
A prov:Collection is an Entity that provides a structure (e.g. set, list, etc.) to some constituents (which are themselves Entities). The prov:Collection class can be used to express the provenance of the collection itself: e.g. who maintained the collection, which members it contained as it evolved, and how it was assembled. The prov:hadMember property is used to assert membership in a collection.
A prov:Bundle is a named set of provenance descriptions, which may itself have provenance. The named set of provenance descriptions may be expressed as PROV-O or any other form. The subclass of Bundle that names a set of PROV-O assertions is not provided by PROV-O, since it is more appropriate to do so using other recommendations, standards, or technologies. In any case, a Bundle of PROV-O assertions is an abstract set of RDF triples, and adding or removing a triple creates a new distinct Bundle of PROV-O assertions.
A prov:Plan is an entity that represents a set of actions or steps intended by one or more agents to achieve some goals.
More general and more specific properties are also provided by the expanded terms. More generally, the property prov:wasInfluencedBy is a superproperty that relates any influenced Entity, Activity, or Agent to any other influencing Entity, Activity, or Agent that had an effect on its characteristics. Three subproperties of prov:wasDerivedFrom are also provided for certain kinds of derivation among Entities: prov:wasQuotedFrom cites a potentially larger Entity (such as a book, blog, or image) from which a new Entity was created by repeating some or all of the original, prov:wasRevisionOf indicates that the derived Entity contains substantial content from the original Entity (e.g., two editions of a book), and prov:hadPrimarySource cites a preceding Entity produced by some agent with direct experience and knowledge about the topic (such as a reading from a sensor, or a journal written during an historical event).
The second category of expanded terms relates Entities according to their levels of abstraction, where some Entities may present more specific aspects than their more general counterparts. While prov:specializationOf links a more specific Entity to a more general one (e.g., today's BBC news home page versus BBC's news home page on any day), prov:alternateOf links Entities that present aspects of the same thing, but not necessarily the same aspects or at the same time (e.g., the serialization of a document in different formats or a backup copy of a computer file).
The third category of expanded terms allows further description of Entities. The property prov:value provides a literal value that is a direct representation of an entity. For example, the prov:value of a quote could be a string of the sentences stated, or the prov:value of an Entity involved in a numeric calculation could be the xsd:integer four. The property prov:atLocation can be used to describe the prov:Location of any Entity, Activity, Agent, or prov:InstantaneousEvent (i.e., the starting or ending of an activity or the generation, usage, or invalidation of an entity). The properties used to describe instances of prov:Location are outside the scope of PROV-O; reuse of other existing vocabulary is encouraged.
The fourth category of expanded terms describes the lifetime of an Entity beyond being generated by an Activity and used by other Activities. For example, a painting could not have been displayed before it was painted, and it could not be sold after it was destroyed by fire. Similar to how Activities have start and end times, an Entity may be bound by points in time for which it was generated or is no longer usable. The properties prov:generatedAtTime and prov:invalidatedAtTime can be used to bound the starting and ending moments of an Entity's existence. The Activities that led to the generation or invalidation of an Entity can be provided using prov:wasGeneratedBy and prov:wasInvalidatedBy, respectively. prov:generated and prov:invalidated are the inverses of prov:wasGeneratedBy and prov:wasInvalidatedBy, respectively, and are defined to facilitate Activity-as-subject as well as Entity-as-subject descriptions. For more about inverses, see the Appendix B.
The fifth category of expanded terms describes the lifetime of an Activity beyond its start and end times and predecessor Activities. Activities may also be started or ended by Entities, which are described using the properties prov:wasStartedBy and prov:wasEndedBy, respectively. Since Entities may start or end Activities, and Agents may be Entities, then Agents may also start or end Activities.
The following examples illustrate the expanded terms by elaborating the crime chart example from the previous section. After aggregating the dataset and creating the chart, Derek published a post to exhibit his work.
Example 2:
Agent :derek, acting again on behalf of the :national_newspaper_inc organization, used the :postEditor tool to publish a post about his recent data analysis :aggregatedByRegions. The blog editing tool tracked Derek's actions as PROV-O assertions and published them as a Bundle (the current file <>). The tool recorded that :derek started and ended the publishing activity (:publicationActivity1123) that generated the post :post9821v1. The post included a permanent link where the content of the latest version is available (:more-crime-happens-in-cities) in addition to a textual snapshot of the current version (using prov:value). Derek also included additional domain-specific descriptions of the post, such as its title.
Shortly after publishing the post, Derek noticed a typographical error in his narrative. Because the fix would be minimal, he did not record the activity that led to the new version. Instead, he related the new version (:post9821v2) as a revision of the previous (:post9821v1). Since both versions of the blog are forms of the long-standing blog permalink :more-crime-happens-in-cities, the revisions are alternates of one another and each is a prov:specializationOf of :more-crime-happens-in-cities.
Figure 4. An illustration of the PROV-O assertions in Example 2, where Derek
published two versions of a blog for the National Newspaper, Inc.
The diagrams in this document depict Entities as yellow ovals, Activities as blue rectangles,
and Agents as orange pentagons. The responsibility properties are shown in pink.
Shortly after Derek published his blog post, Monica adapted the text for a wider audience in a new post (:post9822). This rewrite is an alternate, abbreviated view of the same topic that Derek wrote about and was created from his original text. Since the provenance produced by the activities of Derek and Monica corresponded to different user views, the system automatically published it in a different prov:Bundle. The tool also asserted provenance about the bundle that it produced (e.g., the date of creation, its creator, and the fact that it Derek's bundle was used). Because a bundle is a kind of entity, all provenance assertions that can be made about entities can also be made about bundles. The use of bundles enables the creation of provenance of provenance.
Example 3:
After some time, John wrote his own conclusions in his own post (:post19201) quoting the previous two posts. Each quote that John makes (:quote_from_monica and :quote_from_derek) is a new entity derived from the previous blogs and is annotated with the time that the quote was taken. The provenance of John's blog notes that his post is the result of the quotes that he took from Derek and Monica. The blog post is also derived from Derek's :aggregatedByRegions dataset because John inspected it and found a concern that he discusses in his blog. All the provenance statements related to John's post are grouped in a new prov:Bundle.
Example 4:
Unfortunately, there was a problem in the servers where :post19201 was being stored, and all the data related to the post was lost permanently. Thus, the system invalidated the entity automatically and notified John about the error.
Example 5:

### 3.3 Qualified Terms

The Qualified Terms category is the result of applying the Qualification Pattern [] to the simple (unqualified) relations available in the Starting Point and Expanded categories. The terms in this category are for users who wish to provide further details about the provenance-related influence among Entities, Activities, and Agents.
The Qualification Pattern restates an unqualified influence relation by using an intermediate class that represents the influence between two resources. This new instance, in turn, can be annotated with additional descriptions of the influence that one resource had upon another. The following two tables list the influence relations that can be qualified using the Qualification Pattern, along with the properties used to qualify them. For example, the second row of the first table indicates that to elaborate how an prov:Activity prov:used a particular prov:Entity, one creates an instance of prov:Usage that indicates the influencing entity with the prov:entity property. Meanwhile, the influenced prov:Activity indicates the prov:Usage with the property prov:qualifiedUsage. The resulting structure that qualifies the an Activity's usage of an Entity is illustrated in Figure 4a below.
Seven Starting Point relations can be further described using the Qualification Pattern. They are listed in the following normative table.
Table 2: Qualification Property and Qualified Influence Class used to qualify a Starting-point Property.
Influenced Class
Unqualified Influence
Influencing Class
Qualification Property
Qualified Influence
Influencer Property
Seven Expanded relations can be further described using the Qualification Pattern. They are listed in the following normative table.
Table 3: Qualification Property and Qualified Influence Class used to qualify an Expanded Property.
Influenced Class
Unqualified Influence
Influencing Class
Qualification Property
Qualified Influence
Influencer Property
prov:Entity or prov:Activity or prov:Agent
prov:Entity or prov:Activity or prov:Agent
The qualification classes and properties shown in the previous two tables can also be found in the normative cross reference in the next section of this document. All influence classes (e.g. prov:Association, prov:Usage) are extensions of prov:Influence and either prov:EntityInfluence, prov:ActivityInfluence, or prov:AgentInfluence, which determine the property used to cite the influencing resource (either prov:entity, prov:activity, or prov:agent, respectively). Because prov:Influence is a broad relation, its most specific subclasses (e.g. prov:Communication, prov:Delegation, prov:End, prov:Revision, etc.) should be used when applicable.
Example 6:
For example, given the unqualified statement:
One can find that prov:wasGeneratedBy can be qualified using the qualification property prov:qualifiedGeneration, the class prov:Generation (a subclass of prov:ActivityInfluence), and the property prov:activity. From this, the influence relation above can be restated with the qualification pattern as:
Example 7:
The asserter can thus attach additional properties to :e1Gen to describe the generation of :e1 by :a1.
As can be seen in this example, qualifying an influence relation provides a second form (e.g. :e1 prov:qualifiedGeneration :e1Gen) to express an equivalent influence relation (e.g. :e1 prov:wasGeneratedBy :a1). It is correct and acceptable for an implementer to use either qualified or unqualified forms as they choose (or both), and a consuming application should be prepared to recognize either form. Consuming applications should recognize both qualified and unqualified forms, and treat the qualified form as implying the unqualified form. Because the qualification form is more verbose, the unqualified form should be favored in cases where additional properties are not provided. When the qualified form is expressed, including the equivalent unqualified form can facilitate PROV-O consumption, and is thus encouraged.
In addition to the previous two tables, Figure 4 illustrates the classes and properties needed to apply the qualification pattern to ten of the fourteen qualifiable influence relations. For example, while prov:qualifiedUsage, prov:Usage, and prov:entity are used to qualify prov:used relations, prov:qualifiedAssociation, prov:Association, and prov:agent are used to qualify prov:wasAssociatedWith relations. This pattern applies to the twelve other influence relations that can be qualified.
In subfigure a the prov:qualifiedUsage property parallels the prov:used property and references an instance of prov:Usage, which in turn provides attributes of the prov:used relation between the Activity and Entity. The prov:entity property is used to cite the Entity that was used by the Activity. In this case, the time that the Activity used the Entity is provided using the prov:atTime property and a literal xsd:dateTime value. The prov:atTime property can be used to describe any prov:InstantaneousEvent (including prov:Start, prov:Generation, prov:Usage, prov:Invalidation, and prov:End).
Similarly in subfigure j, the prov:qualifiedAssociation property parallels the prov:wasAssociatedWith property and references an instance of prov:Association, which in turn provides attributes of the prov:wasAssociatedWith relation between the Activity and Agent. The prov:agent property is used to cite the Agent that influenced the Activity. In this case, the plan of actions and steps that the Agent used to achieve its goals is provided using the prov:hadPlan property and an instance of prov:Plan. Further, the prov:hadRole property and prov:Role class can be used to describe the function that the agent served with respect to the Activity. Both prov:Plan and prov:Role are left to be extended by applications.
Figure 4: Illustration of the properties and classes to use (in blue) to qualify the starting point and expanded influence relations (dotted black).
The diagrams in this document depict Entities as ovals, Activities as rectangles, and Agents as pentagons. Quotation, Revision, and PrimarySource are omitted because they are special forms of Derivation and follow the same pattern as subfigure g.
The following two examples show the result of applying the Usage and Association patterns to the chart-making example from Section 3.1.
Example 8:
Qualified Usage
The prov:qualifiedUsage property parallels the prov:used property to provide an additional description to :illustrationActivity. The instance of prov:Usage cites the data used (:aggregatedByRegions) and the time the activity used it (2011-07-14T03:03:03Z).
Example 9:
Qualified Association
The prov:qualifiedAssociation property parallels the prov:wasAssociatedWith property to provide an additional description about the :illustrationActivity that Derek influenced. The instance of prov:Association cites the influencing agent (:derek) that followed the instructions (:tutorial_blog). Further, Derek served the role of :illustrationist during the activity.
This section finishes with two more examples of qualification as applied to the chart-making example from Section 3.1.
Example 10:
Qualified Generation
The prov:qualifiedGeneration property parallels the prov:wasGeneratedBy property to provide an additional description to :bar_chart. The instance of prov:Generation cites the time (2011-07-14T15:52:14Z) that the activity (:illustrationActivity) generated the chart (:bar_chart).
Example 11:
Qualified Derivation
The prov:qualifiedDerivation property parallels the prov:wasDerivedFrom property to provide an additional description to :bar_chart. The instance of prov:Derivation cites the activity (:illustrationActivity) and the Usages and Generations that the activity conduced to create the :bar_chart.

## 4. Cross reference for PROV-O classes and properties

This section provides details for each class and property defined by the PROV Ontology, grouped by the categories described above:
- Starting Point Terms
- Expanded Terms
- Qualified Terms
The superscripts op and dp denote that a property is an OWL object property or data property, respectively.
Each PROV-O term in this cross reference links to the corresponding PROV-DM concept. The PROV-DM's table Cross-References to PROV-O and PROV-N provides an overview of the correspondences between PROV-O and PROV-DM.
The qualification classes and properties shown in Table 2 and Table 3 of the previous section can also be found in each entry of this cross reference. If the property can be qualified, the can be qualified with header indicates the qualifying property and influence class that should be used. Conversely, the qualifies headers in the listings for qualification terms indicate the unqualified property that they qualify. In the OWL file itself, the annotation properties prov:qualifiedForm and prov:unqualifiedForm provide the same linkages between the unqualified properties and their qualifiying terms.
Most examples shown in this cross reference are encoded using the Turtle RDF serialization. When it is convenient to do so (e.g., when an example describes a prov:Bundle), it may use the [] syntax. Although this document does not specify how to encode Bundles in RDF, TriG's named graph construct is used only to illustrate the concept of creating a named set of PROV assertions. Note that all examples are non-normative.

### 4.1 Starting Point Terms

The classes and properties that provide a basis for all other PROV-O terms are discussed in Section 3.1.

### (1) Class: prov:Entity back to starting-point classes

IRI:
An entity is a physical, digital, conceptual, or other kind of thing with some fixed aspects; entities may be real or imaginary.
described with properties:
prov:invalidatedAtTime dp , prov:wasAttributedTo op , prov:qualifiedGeneration op , prov:wasGeneratedBy op , prov:wasDerivedFrom op , prov:specializationOf op , prov:qualifiedDerivation op , prov:qualifiedInvalidation op , prov:generatedAtTime dp , prov:qualifiedQuotation op , prov:hadPrimarySource op , prov:qualifiedPrimarySource op , prov:alternateOf op , prov:value dp , prov:wasInvalidatedBy op , prov:qualifiedAttribution op , prov:wasQuotedFrom op , prov:qualifiedRevision op , prov:wasRevisionOf op
prov:wasInfluencedBy op , prov:qualifiedInfluence op , prov:atLocation op
in range of
prov:hadPrimarySource op prov:generated op prov:wasDerivedFrom op prov:entity op prov:specializationOf op prov:invalidated op prov:used op prov:hadMember op prov:alternateOf op prov:wasStartedBy op prov:wasQuotedFrom op prov:wasEndedBy op prov:wasRevisionOf op
has subclasses
PROV-DM term
entity

### (2) Class: prov:Activity back to starting-point classes

IRI:
An activity is something that occurs over a period of time and acts upon or with entities; it may include consuming, processing, transforming, modifying, relocating, using, or generating entities.
described with properties:
prov:generated op , prov:qualifiedAssociation op , prov:wasAssociatedWith op , prov:qualifiedEnd op , prov:wasEndedBy op , prov:qualifiedUsage op , prov:used op , prov:invalidated op , prov:endedAtTime dp , prov:qualifiedStart op , prov:wasInformedBy op , prov:wasStartedBy op , prov:startedAtTime dp , prov:qualifiedCommunication op
prov:wasInfluencedBy op , prov:qualifiedInfluence op , prov:atLocation op
in range of
prov:activity op prov:wasInformedBy op prov:wasGeneratedBy op prov:hadActivity op prov:wasInvalidatedBy op
PROV-DM term
Activity

### (3) Class: prov:Agent back to starting-point classes

IRI:
An agent is something that bears some form of responsibility for an activity taking place, for the existence of an entity, or for another agent's activity.
described with properties:
prov:actedOnBehalfOf op , prov:qualifiedDelegation op
prov:wasInfluencedBy op , prov:qualifiedInfluence op , prov:atLocation op
in range of
prov:actedOnBehalfOf op prov:agent op prov:wasAssociatedWith op prov:wasAttributedTo op
has subclasses
PROV-DM term
agent

### (4) Property: prov:wasGeneratedBy op back to starting-point properties

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedGeneration op
PROV-DM term
Generation

### (5) Property: prov:wasDerivedFrom op back to starting-point properties

IRI:
A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.
The more specific subproperties of prov:wasDerivedFrom (i.e., prov:wasQuotedFrom, prov:wasRevisionOf, prov:hadPrimarySource) should be used when applicable.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
has sub-properties
can be qualified with
- prov:qualifiedDerivation op
PROV-DM term
Derivation

### (6) Property: prov:wasAttributedTo op back to starting-point properties

IRI:
Attribution is the ascribing of an entity to an agent.
Attribution is the ascribing of an entity to an agent.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedAttribution op
PROV-DM term
attribution

### (7) Property: prov:startedAtTime dp back to starting-point properties

IRI:
Start is when an activity is deemed to have been started by an entity, known as trigger. The activity did not exist before its start. Any usage, generation, or invalidation involving an activity follows the activity's start. A start may refer to a trigger entity that set off the activity, or to an activity, known as starter, that generated the trigger.
The time at which an activity started. See also prov:endedAtTime.
has domain
has range
can be qualified with
- prov:atTime dp
PROV-DM term
Start

### (8) Property: prov:used op back to starting-point properties

IRI:
Usage is the beginning of utilizing an entity by an activity. Before usage, the activity had not begun to utilize this entity and could not have been affected by the entity.
A prov:Entity that was used by this prov:Activity. For example, :baking prov:used :spoon, :egg, :oven .
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedUsage op
PROV-DM term
Usage

### (9) Property: prov:wasInformedBy op back to starting-point properties

IRI:
Communication is the exchange of an entity by two activities, one activity using the entity generated by the other.
An activity a2 is dependent on or informed by another activity a1, by way of some unspecified entity that is generated by a1 and used by a2.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedCommunication op
PROV-DM term
Communication

### (10) Property: prov:endedAtTime dp back to starting-point properties

IRI:
End is when an activity is deemed to have been ended by an entity, known as trigger. The activity no longer exists after its end. Any usage, generation, or invalidation involving an activity precedes the activity's end. An end may refer to a trigger entity that terminated the activity, or to an activity, known as ender that generated the trigger.
The time at which an activity ended. See also prov:startedAtTime.
has domain
has range
can be qualified with
- prov:atTime dp
PROV-DM term
End

### (11) Property: prov:wasAssociatedWith op back to starting-point properties

IRI:
An activity association is an assignment of responsibility to an agent for an activity, indicating that the agent had a role in the activity. It further allows for a plan to be specified, which is the plan intended by the agent to achieve some goals in the context of this activity.
An prov:Agent that had some (unspecified) responsibility for the occurrence of this prov:Activity.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedAssociation op
PROV-DM term
Association

### (12) Property: prov:actedOnBehalfOf op back to starting-point properties

IRI:
Delegation is the assignment of authority and responsibility to an agent (by itself or by another agent) to carry out a specific activity as a delegate or representative, while the agent it acts on behalf of retains some responsibility for the outcome of the delegated work. For example, a student acted on behalf of his supervisor, who acted on behalf of the department chair, who acted on behalf of the university; all those agents are responsible in some way for the activity that took place but we do not say explicitly who bears responsibility and to what degree.
An object property to express the accountability of an agent towards another agent. The subordinate agent acted on behalf of the responsible agent in an actual activity.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedDelegation op
PROV-DM term
delegation

### 4.2 Expanded Terms

The additional terms used to describe relations among Starting Point classes are discussed in Section 3.2.

### (13) Class: prov:Collection back to expanded classes

IRI:
A collection is an entity that provides a structure to some constituents, which are themselves entities. These constituents are said to be member of the collections.
is subclass of
described with properties:
prov:hadMember op
has subclass
PROV-DM term
collection

### (14) Class: prov:EmptyCollection back to expanded classes

IRI:
An empty collection is a collection without members.
is subclass of
described with properties:
prov:hadMember op

### (15) Class: prov:Bundle back to expanded classes

IRI:
A bundle is a named set of provenance descriptions, and is itself an Entity, so allowing provenance of provenance to be expressed.
Note that there are kinds of bundles (e.g. handwritten letters, audio recordings, etc.) that are not expressed in PROV-O, but can be still be described by PROV-O.
is subclass of
PROV-DM term
bundle-entity

### (16) Class: prov:Person back to expanded classes

IRI:
Person agents are people.
is subclass of
described with properties:
prov:qualifiedDelegation op , prov:actedOnBehalfOf op
PROV-DM term
agent

### (17) Class: prov:SoftwareAgent back to expanded classes

IRI:
A software agent is running software.
is subclass of
described with properties:
prov:qualifiedDelegation op , prov:actedOnBehalfOf op
PROV-DM term
agent

### (18) Class: prov:Organization back to expanded classes

IRI:
An organization is a social or legal institution such as a company, society, etc.
is subclass of
described with properties:
prov:qualifiedDelegation op , prov:actedOnBehalfOf op
PROV-DM term
agent

### (19) Class: prov:Location back to expanded classes

IRI:
A location can be an identifiable geographic place (ISO 19112), but it can also be a non-geographic place such as a directory, row, or column. As such, there are numerous ways in which location can be expressed, such as by a coordinate, address, landmark, and so forth.
in range of
prov:atLocation op
PROV-DM term
attribute-location

### (20) Property: prov:alternateOf op back to expanded properties

IRI:
Two alternate entities present aspects of the same thing. These aspects may be the same or different, and the alternate entities may or may not overlap in time.
has domain
has range
has sub-properties
PROV-DM term
alternate

### (21) Property: prov:specializationOf op back to expanded properties

IRI:
An entity that is a specialization of another shares all aspects of the latter, and additionally presents more specific aspects of the same thing as the latter. In particular, the lifetime of the entity being specialized contains that of any specialization. Examples of aspects include a time period, an abstraction, and a context associated with the entity.
has super-properties
- prov:alternateOf op
has domain
has range
PROV-DM term
specialization

### (22) Property: prov:generatedAtTime dp back to expanded properties

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
The time at which an entity was completely created and is available for use.
has domain
has range
can be qualified with
- prov:atTime dp
PROV-DM term
Generation

### (23) Property: prov:hadPrimarySource op back to expanded properties

IRI:
A primary source for a topic refers to something produced by some agent with direct experience and knowledge about the topic, at the time of the topic's study, without benefit from hindsight. Because of the directness of primary sources, they 'speak for themselves' in ways that cannot be captured through the filter of secondary sources. As such, it is important for secondary sources to reference those primary sources from which they were derived, so that their reliability can be investigated. A primary source relation is a particular case of derivation of secondary materials from their primary sources. It is recognized that the determination of primary sources can be up to interpretation, and should be done according to conventions accepted within the application's domain.
has super-properties
- prov:wasDerivedFrom op
has domain
has range
can be qualified with
- prov:qualifiedPrimarySource op
PROV-DM term
primary-source

### (24) Property: prov:value dp back to expanded properties

IRI:
Provides a value that is a direct representation of an entity.
has domain
PROV-DM term
attribute-value

### (25) Property: prov:wasQuotedFrom op back to expanded properties

IRI:
A quotation is the repeat of (some or all of) an entity, such as text or image, by someone who may or may not be its original author. Quotation is a particular case of derivation.
An entity is derived from an original entity by copying, or 'quoting', some or all of it.
has super-properties
- prov:wasDerivedFrom op
has domain
has range
can be qualified with
- prov:qualifiedQuotation op
PROV-DM term
quotation

### (26) Property: prov:wasRevisionOf op back to expanded properties

IRI:
A revision is a derivation for which the resulting entity is a revised version of some original. The implication here is that the resulting entity contains substantial content from the original. Revision is a particular case of derivation.
A revision is a derivation that revises an entity into a revised version.
has super-properties
- prov:wasDerivedFrom op
has domain
has range
can be qualified with
- prov:qualifiedRevision op
PROV-DM term
revision

### (27) Property: prov:invalidatedAtTime dp back to expanded properties

IRI:
Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.
The time at which an entity was invalidated (i.e., no longer usable).
has domain
has range
can be qualified with
- prov:atTime dp
PROV-DM term
Invalidation

### (28) Property: prov:wasInvalidatedBy op back to expanded properties

IRI:
Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedInvalidation op
PROV-DM term
Invalidation

### (29) Property: prov:hadMember op back to expanded properties

IRI:
A collection is an entity that provides a structure to some constituents, which are themselves entities. These constituents are said to be member of the collections.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
PROV-DM term
collection

### (30) Property: prov:wasStartedBy op back to expanded properties

IRI:
Start is when an activity is deemed to have been started by an entity, known as trigger. The activity did not exist before its start. Any usage, generation, or invalidation involving an activity follows the activity's start. A start may refer to a trigger entity that set off the activity, or to an activity, known as starter, that generated the trigger.
Start is when an activity is deemed to have started. A start may refer to an entity, known as trigger, that initiated the activity.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedStart op
PROV-DM term
Start

### (31) Property: prov:wasEndedBy op back to expanded properties

IRI:
End is when an activity is deemed to have been ended by an entity, known as trigger. The activity no longer exists after its end. Any usage, generation, or invalidation involving an activity precedes the activity's end. An end may refer to a trigger entity that terminated the activity, or to an activity, known as ender that generated the trigger.
End is when an activity is deemed to have ended. An end may refer to an entity, known as trigger, that terminated the activity.
has super-properties
- prov:wasInfluencedBy op
has domain
has range
can be qualified with
- prov:qualifiedEnd op
PROV-DM term
End

### (32) Property: prov:invalidated op back to expanded properties

IRI:
Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.
has super-properties
- prov:influenced op
has domain
has range
has inverse
PROV-DM term
Invalidation

### (33) Property: prov:influenced op back to expanded properties

IRI:
Influence is the capacity of an entity, activity, or agent to have an effect on the character, development, or behavior of another by means of usage, start, end, generation, invalidation, communication, derivation, attribution, association, or delegation.
has inverse
has sub-properties
PROV-DM term
influence

### (34) Property: prov:atLocation op back to expanded properties

IRI:
A location can be an identifiable geographic place (ISO 19112), but it can also be a non-geographic place such as a directory, row, or column. As such, there are numerous ways in which location can be expressed, such as by a coordinate, address, landmark, and so forth.
The Location of any resource.
This property has multiple RDFS domains to suit multiple OWL Profiles. See PROV-O OWL Profile.
has domain
- prov:Activity or prov:Agent or prov:Entity or prov:InstantaneousEvent
has range
PROV-DM term
attribute-location

### (35) Property: prov:generated op back to expanded properties

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
has super-properties
- prov:influenced op
has domain
has range
has inverse
PROV-DM term
Generation

### 4.3 Qualified Terms

The terms used to qualify the Starting Point and Expanded properties are discussed in Section 3.3.

### (36) Class: prov:Influence back to qualified classes

IRI:
Influence is the capacity of an entity, activity, or agent to have an effect on the character, development, or behavior of another by means of usage, start, end, generation, invalidation, communication, derivation, attribution, association, or delegation.
Because prov:Influence is a broad relation, its most specific subclasses (e.g. prov:Communication, prov:Delegation, prov:End, prov:Revision, etc.) should be used when applicable.
An instance of prov:Influence provides additional descriptions about the binary prov:wasInfluencedBy relation from some influenced Activity, Entity, or Agent to the influencing Activity, Entity, or Agent. For example, :stomach_ache prov:wasInfluencedBy :spoon; prov:qualifiedInfluence [ a prov:Influence; prov:entity :spoon; :foo :bar ] . Because prov:Influence is a broad relation, the more specific relations (Communication, Delegation, End, etc.) should be used when applicable.
described with properties:
prov:influencer op , prov:hadRole op , prov:hadActivity op
in range of
prov:qualifiedInfluence op
has subclasses
qualifies
prov:wasInfluencedBy op
PROV-DM term
influence

### (37) Class: prov:EntityInfluence back to qualified classes

IRI:
EntityInfluence is the capacity of an entity to have an effect on the character, development, or behavior of another by means of usage, start, end, derivation, or other.
EntityInfluence provides additional descriptions of an Entity's binary influence upon any other kind of resource. Instances of EntityInfluence use the prov:entity property to cite the influencing Entity.
It is not recommended that the type EntityInfluence be asserted without also asserting one of its more specific subclasses.
is subclass of
described with properties:
prov:entity op
prov:hadRole op , prov:influencer op , prov:hadActivity op
has subclasses

### (38) Class: prov:Usage back to qualified classes

IRI:
Usage is the beginning of utilizing an entity by an activity. Before usage, the activity had not begun to utilize this entity and could not have been affected by the entity.
An instance of prov:Usage provides additional descriptions about the binary prov:used relation from some prov:Activity to an prov:Entity that it used. For example, :keynote prov:used :podium; prov:qualifiedUsage [ a prov:Usage; prov:entity :podium; :foo :bar ].
is subclass of
described with properties:
prov:atTime dp , prov:entity op
in range of
prov:hadUsage op prov:qualifiedUsage op
qualifies
prov:used op
PROV-DM term
Usage

### (39) Class: prov:Start back to qualified classes

IRI:
Start is when an activity is deemed to have been started by an entity, known as trigger. The activity did not exist before its start. Any usage, generation, or invalidation involving an activity follows the activity's start. A start may refer to a trigger entity that set off the activity, or to an activity, known as starter, that generated the trigger.
An instance of prov:Start provides additional descriptions about the binary prov:wasStartedBy relation from some started prov:Activity to an prov:Entity that started it. For example, :foot_race prov:wasStartedBy :bang; prov:qualifiedStart [ a prov:Start; prov:entity :bang; :foo :bar; prov:atTime '2012-03-09T08:05:08-05:00'^^xsd:dateTime ] .
is subclass of
described with properties:
prov:hadActivity op
prov:atTime dp , prov:entity op
in range of
prov:qualifiedStart op
qualifies
prov:wasStartedBy op
PROV-DM term
Start

### (40) Class: prov:End back to qualified classes

IRI:
End is when an activity is deemed to have been ended by an entity, known as trigger. The activity no longer exists after its end. Any usage, generation, or invalidation involving an activity precedes the activity's end. An end may refer to a trigger entity that terminated the activity, or to an activity, known as ender that generated the trigger.
An instance of prov:End provides additional descriptions about the binary prov:wasEndedBy relation from some ended prov:Activity to an prov:Entity that ended it. For example, :ball_game prov:wasEndedBy :buzzer; prov:qualifiedEnd [ a prov:End; prov:entity :buzzer; :foo :bar; prov:atTime '2012-03-09T08:05:08-05:00'^^xsd:dateTime ].
is subclass of
described with properties:
prov:hadActivity op
prov:atTime dp , prov:entity op
in range of
prov:qualifiedEnd op
qualifies
prov:wasEndedBy op
PROV-DM term
End

### (41) Class: prov:Derivation back to qualified classes

IRI:
A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.
The more specific forms of prov:Derivation (i.e., prov:Revision, prov:Quotation, prov:PrimarySource) should be asserted if they apply.
An instance of prov:Derivation provides additional descriptions about the binary prov:wasDerivedFrom relation from some derived prov:Entity to another prov:Entity from which it was derived. For example, :chewed_bubble_gum prov:wasDerivedFrom :unwrapped_bubble_gum; prov:qualifiedDerivation [ a prov:Derivation; prov:entity :unwrapped_bubble_gum; :foo :bar ].
is subclass of
described with properties:
prov:hadUsage op , prov:hadGeneration op
prov:hadActivity op
prov:entity op
in range of
prov:qualifiedDerivation op
has subclasses
qualifies
prov:wasDerivedFrom op
PROV-DM term
Derivation

### (42) Class: prov:PrimarySource back to qualified classes

IRI:
A primary source for a topic refers to something produced by some agent with direct experience and knowledge about the topic, at the time of the topic's study, without benefit from hindsight. Because of the directness of primary sources, they 'speak for themselves' in ways that cannot be captured through the filter of secondary sources. As such, it is important for secondary sources to reference those primary sources from which they were derived, so that their reliability can be investigated. A primary source relation is a particular case of derivation of secondary materials from their primary sources. It is recognized that the determination of primary sources can be up to interpretation, and should be done according to conventions accepted within the application's domain.
An instance of prov:PrimarySource provides additional descriptions about the binary prov:hadPrimarySource relation from some secondary prov:Entity to an earlier, primary prov:Entity. For example, :blog prov:hadPrimarySource :newsArticle; prov:qualifiedPrimarySource [ a prov:PrimarySource; prov:entity :newsArticle; :foo :bar ] .
is subclass of
described with properties:
prov:hadGeneration op , prov:hadUsage op
in range of
prov:qualifiedPrimarySource op
qualifies
prov:hadPrimarySource op
PROV-DM term
primary-source

### (43) Class: prov:Quotation back to qualified classes

IRI:
A quotation is the repeat of (some or all of) an entity, such as text or image, by someone who may or may not be its original author. Quotation is a particular case of derivation.
An instance of prov:Quotation provides additional descriptions about the binary prov:wasQuotedFrom relation from some taken prov:Entity from an earlier, larger prov:Entity. For example, :here_is_looking_at_you_kid prov:wasQuotedFrom :casablanca_script; prov:qualifiedQuotation [ a prov:Quotation; prov:entity :casablanca_script; :foo :bar ].
is subclass of
described with properties:
prov:hadGeneration op , prov:hadUsage op
in range of
prov:qualifiedQuotation op
qualifies
prov:wasQuotedFrom op
PROV-DM term
quotation

### (44) Class: prov:Revision back to qualified classes

IRI:
A revision is a derivation for which the resulting entity is a revised version of some original. The implication here is that the resulting entity contains substantial content from the original. Revision is a particular case of derivation.
An instance of prov:Revision provides additional descriptions about the binary prov:wasRevisionOf relation from some newer prov:Entity to an earlier prov:Entity. For example, :draft_2 prov:wasRevisionOf :draft_1; prov:qualifiedRevision [ a prov:Revision; prov:entity :draft_1; :foo :bar ].
is subclass of
described with properties:
prov:hadGeneration op , prov:hadUsage op
in range of
prov:qualifiedRevision op
qualifies
prov:wasRevisionOf op
PROV-DM term
revision

### (45) Class: prov:ActivityInfluence back to qualified classes

IRI:
ActivitiyInfluence is the capacity of an activity to have an effect on the character, development, or behavior of another by means of generation, invalidation, communication, or other.
It is not recommended that the type ActivityInfluence be asserted without also asserting one of its more specific subclasses.
ActivityInfluence provides additional descriptions of an Activity's binary influence upon any other kind of resource. Instances of ActivityInfluence use the prov:activity property to cite the influencing Activity.
is subclass of
described with properties:
prov:activity op
prov:hadRole op , prov:influencer op , prov:hadActivity op
has subclasses

### (46) Class: prov:Generation back to qualified classes

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
An instance of prov:Generation provides additional descriptions about the binary prov:wasGeneratedBy relation from a generated prov:Entity to the prov:Activity that generated it. For example, :cake prov:wasGeneratedBy :baking; prov:qualifiedGeneration [ a prov:Generation; prov:activity :baking; :foo :bar ].
is subclass of
described with properties:
prov:activity op , prov:atTime dp
in range of
prov:hadGeneration op prov:qualifiedGeneration op
qualifies
prov:wasGeneratedBy op
PROV-DM term
Generation

### (47) Class: prov:Communication back to qualified classes

IRI:
Communication is the exchange of an entity by two activities, one activity using the entity generated by the other.
An instance of prov:Communication provides additional descriptions about the binary prov:wasInformedBy relation from an informed prov:Activity to the prov:Activity that informed it. For example, :you_jumping_off_bridge prov:wasInformedBy :everyone_else_jumping_off_bridge; prov:qualifiedCommunication [ a prov:Communication; prov:activity :everyone_else_jumping_off_bridge; :foo :bar ].
is subclass of
described with properties:
prov:activity op
in range of
prov:qualifiedCommunication op
qualifies
prov:wasInformedBy op
PROV-DM term
Communication

### (48) Class: prov:Invalidation back to qualified classes

IRI:
Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.
An instance of prov:Invalidation provides additional descriptions about the binary prov:wasInvalidatedBy relation from an invalidated prov:Entity to the prov:Activity that invalidated it. For example, :uncracked_egg prov:wasInvalidatedBy :baking; prov:qualifiedInvalidation [ a prov:Invalidation; prov:activity :baking; :foo :bar ].
is subclass of
described with properties:
prov:activity op , prov:atTime dp
in range of
prov:qualifiedInvalidation op
qualifies
prov:wasInvalidatedBy op
PROV-DM term
Invalidation

### (49) Class: prov:AgentInfluence back to qualified classes

IRI:
AgentInfluence is the capacity of an agent to have an effect on the character, development, or behavior of another by means of attribution, association, delegation, or other.
AgentInfluence provides additional descriptions of an Agent's binary influence upon any other kind of resource. Instances of AgentInfluence use the prov:agent property to cite the influencing Agent.
It is not recommended that the type AgentInfluence be asserted without also asserting one of its more specific subclasses.
is subclass of
described with properties:
prov:agent op
prov:hadRole op , prov:influencer op , prov:hadActivity op
has subclasses

### (50) Class: prov:Attribution back to qualified classes

IRI:
Attribution is the ascribing of an entity to an agent. When an entity e is attributed to agent ag, entity e was generated by some unspecified activity that in turn was associated to agent ag. Thus, this relation is useful when the activity is not known, or irrelevant.
An instance of prov:Attribution provides additional descriptions about the binary prov:wasAttributedTo relation from an prov:Entity to some prov:Agent that had some responsible for it. For example, :cake prov:wasAttributedTo :baker; prov:qualifiedAttribution [ a prov:Attribution; prov:entity :baker; :foo :bar ].
is subclass of
described with properties:
prov:agent op
in range of
prov:qualifiedAttribution op
qualifies
prov:wasAttributedTo op
PROV-DM term
attribution

### (51) Class: prov:Association back to qualified classes

IRI:
An activity association is an assignment of responsibility to an agent for an activity, indicating that the agent had a role in the activity. It further allows for a plan to be specified, which is the plan intended by the agent to achieve some goals in the context of this activity.
An instance of prov:Association provides additional descriptions about the binary prov:wasAssociatedWith relation from an prov:Activity to some prov:Agent that had some responsiblity for it. For example, :baking prov:wasAssociatedWith :baker; prov:qualifiedAssociation [ a prov:Association; prov:agent :baker; :foo :bar ].
is subclass of
described with properties:
prov:hadPlan op
prov:hadRole op
prov:agent op
in range of
prov:qualifiedAssociation op
qualifies
prov:wasAssociatedWith op
PROV-DM term
Association

### (52) Class: prov:Plan back to qualified classes

IRI:
A plan is an entity that represents a set of actions or steps intended by one or more agents to achieve some goals.
There exist no prescriptive requirement on the nature of plans, their representation, the actions or steps they consist of, or their intended goals. Since plans may evolve over time, it may become necessary to track their provenance, so plans themselves are entities. Representing the plan explicitly in the provenance can be useful for various tasks: for example, to validate the execution as represented in the provenance record, to manage expectation failures, or to provide explanations.
is subclass of
in range of
prov:hadPlan op
PROV-DM term
Association

### (53) Class: prov:Delegation back to qualified classes

IRI:
Delegation is the assignment of authority and responsibility to an agent (by itself or by another agent) to carry out a specific activity as a delegate or representative, while the agent it acts on behalf of retains some responsibility for the outcome of the delegated work. For example, a student acted on behalf of his supervisor, who acted on behalf of the department chair, who acted on behalf of the university; all those agents are responsible in some way for the activity that took place but we do not say explicitly who bears responsibility and to what degree.
An instance of prov:Delegation provides additional descriptions about the binary prov:actedOnBehalfOf relation from a performing prov:Agent to some prov:Agent for whom it was performed. For example, :mixing prov:wasAssociatedWith :toddler . :toddler prov:actedOnBehalfOf :mother; prov:qualifiedDelegation [ a prov:Delegation; prov:entity :mother; :foo :bar ].
is subclass of
described with properties:
prov:hadActivity op
prov:agent op
in range of
prov:qualifiedDelegation op
qualifies
prov:actedOnBehalfOf op
PROV-DM term
delegation

### (54) Class: prov:InstantaneousEvent back to qualified classes

IRI:
The PROV data model is implicitly based on a notion of instantaneous events (or just events), that mark transitions in the world. Events include generation, usage, or invalidation of entities, as well as starting or ending of activities. This notion of event is not first-class in the data model, but it is useful for explaining its other concepts and its semantics.
An instantaneous event, or event for short, happens in the world and marks a change in the world, in its activities and in its entities. The term 'event' is commonly used in process algebra with a similar meaning. Events represent communications or interactions; they are assumed to be atomic and instantaneous.
described with properties:
prov:atTime dp
prov:hadRole op , prov:atLocation op
has subclasses

### (55) Class: prov:Role back to qualified classes

IRI:
A role is the function of an entity or agent with respect to an activity, in the context of a usage, generation, invalidation, association, start, and end.
in range of
prov:hadRole op
PROV-DM term
attribute-role

### (56) Property: prov:wasInfluencedBy op back to qualified properties

IRI:
Influence is the capacity of an entity, activity, or agent to have an effect on the character, development, or behavior of another by means of usage, start, end, generation, invalidation, communication, derivation, attribution, association, or delegation.
Because prov:wasInfluencedBy is a broad relation, its more specific subproperties (e.g. prov:wasInformedBy, prov:actedOnBehalfOf, prov:wasEndedBy, etc.) should be used when applicable.
This property has multiple RDFS domains to suit multiple OWL Profiles. See PROV-O OWL Profile.
has domain
- prov:Activity or prov:Agent or prov:Entity
has range
- prov:Activity or prov:Agent or prov:Entity
has sub-properties
can be qualified with
- prov:qualifiedInfluence op
PROV-DM term
influence

### (57) Property: prov:qualifiedInfluence op back to qualified properties

IRI:
Influence is the capacity of an entity, activity, or agent to have an effect on the character, development, or behavior of another by means of usage, start, end, generation, invalidation, communication, derivation, attribution, association, or delegation.
Because prov:qualifiedInfluence is a broad relation, the more specific relations (qualifiedCommunication, qualifiedDelegation, qualifiedEnd, etc.) should be used when applicable.
has domain
- prov:Activity or prov:Agent or prov:Entity
has range
has sub-properties
qualifies
prov:wasInfluencedBy op
PROV-DM term
influence

### (58) Property: prov:qualifiedGeneration op back to qualified properties

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
If this Activity prov:generated Entity :e, then it can qualify how it performed the Generation using prov:qualifiedGeneration [ a prov:Generation; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasGeneratedBy op
PROV-DM term
Generation

### (59) Property: prov:qualifiedDerivation op back to qualified properties

IRI:
A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.
If this Entity prov:wasDerivedFrom Entity :e, then it can qualify how it was derived using prov:qualifiedDerivation [ a prov:Derivation; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasDerivedFrom op
PROV-DM term
Derivation

### (60) Property: prov:qualifiedPrimarySource op back to qualified properties

IRI:
A primary source for a topic refers to something produced by some agent with direct experience and knowledge about the topic, at the time of the topic's study, without benefit from hindsight. Because of the directness of primary sources, they 'speak for themselves' in ways that cannot be captured through the filter of secondary sources. As such, it is important for secondary sources to reference those primary sources from which they were derived, so that their reliability can be investigated. A primary source relation is a particular case of derivation of secondary materials from their primary sources. It is recognized that the determination of primary sources can be up to interpretation, and should be done according to conventions accepted within the application's domain.
If this Entity prov:hadPrimarySource Entity :e, then it can qualify how using prov:qualifiedPrimarySource [ a prov:PrimarySource; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:hadPrimarySource op
PROV-DM term
primary-source

### (61) Property: prov:qualifiedQuotation op back to qualified properties

IRI:
A quotation is the repeat of (some or all of) an entity, such as text or image, by someone who may or may not be its original author. Quotation is a particular case of derivation.
If this Entity prov:wasQuotedFrom Entity :e, then it can qualify how using prov:qualifiedQuotation [ a prov:Quotation; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasQuotedFrom op
PROV-DM term
quotation

### (62) Property: prov:qualifiedRevision op back to qualified properties

IRI:
A revision is a derivation for which the resulting entity is a revised version of some original. The implication here is that the resulting entity contains substantial content from the original. Revision is a particular case of derivation.
If this Entity prov:wasRevisionOf Entity :e, then it can qualify how it was revised using prov:qualifiedRevision [ a prov:Revision; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasRevisionOf op
PROV-DM term
revision

### (63) Property: prov:qualifiedAttribution op back to qualified properties

IRI:
Attribution is the ascribing of an entity to an agent. When an entity e is attributed to agent ag, entity e was generated by some unspecified activity that in turn was associated to agent ag. Thus, this relation is useful when the activity is not known, or irrelevant.
If this Entity prov:wasAttributedTo Agent :ag, then it can qualify how it was influenced using prov:qualifiedAttribution [ a prov:Attribution; prov:agent :ag; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasAttributedTo op
PROV-DM term
attribution

### (64) Property: prov:qualifiedInvalidation op back to qualified properties

IRI:
Invalidation is the start of the destruction, cessation, or expiry of an existing entity by an activity. The entity is no longer available for use (or further invalidation) after invalidation. Any generation or usage of an entity precedes its invalidation.
If this Entity prov:wasInvalidatedBy Activity :a, then it can qualify how it was invalidated using prov:qualifiedInvalidation [ a prov:Invalidation; prov:activity :a; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasInvalidatedBy op
PROV-DM term
Invalidation

### (65) Property: prov:qualifiedStart op back to qualified properties

IRI:
Start is when an activity is deemed to have been started by an entity, known as trigger. The activity did not exist before its start. Any usage, generation, or invalidation involving an activity follows the activity's start. A start may refer to a trigger entity that set off the activity, or to an activity, known as starter, that generated the trigger.
If this Activity prov:wasStartedBy Entity :e1, then it can qualify how it was started using prov:qualifiedStart [ a prov:Start; prov:entity :e1; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasStartedBy op
PROV-DM term
Start

### (66) Property: prov:qualifiedUsage op back to qualified properties

IRI:
Usage is the beginning of utilizing an entity by an activity. Before usage, the activity had not begun to utilize this entity and could not have been affected by the entity.
If this Activity prov:used Entity :e, then it can qualify how it used it using prov:qualifiedUsage [ a prov:Usage; prov:entity :e; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:used op
PROV-DM term
Usage

### (67) Property: prov:qualifiedCommunication op back to qualified properties

IRI:
Communication is the exchange of an entity by two activities, one activity using the entity generated by the other.
If this Activity prov:wasInformedBy Activity :a, then it can qualify how it was influenced using prov:qualifiedCommunication [ a prov:Communication; prov:activity :a; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
can be qualified with
PROV-DM term
Communication

### (68) Property: prov:qualifiedAssociation op back to qualified properties

IRI:
An activity association is an assignment of responsibility to an agent for an activity, indicating that the agent had a role in the activity. It further allows for a plan to be specified, which is the plan intended by the agent to achieve some goals in the context of this activity.
If this Activity prov:wasAssociatedWith Agent :ag, then it can qualify the Association using prov:qualifiedAssociation [ a prov:Association; prov:agent :ag; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasAssociatedWith op
PROV-DM term
Association

### (69) Property: prov:qualifiedEnd op back to qualified properties

IRI:
End is when an activity is deemed to have been ended by an entity, known as trigger. The activity no longer exists after its end. Any usage, generation, or invalidation involving an activity precedes the activity's end. An end may refer to a trigger entity that terminated the activity, or to an activity, known as ender that generated the trigger.
If this Activity prov:wasEndedBy Entity :e1, then it can qualify how it was ended using prov:qualifiedEnd [ a prov:End; prov:entity :e1; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:wasEndedBy op
PROV-DM term
End

### (70) Property: prov:qualifiedDelegation op back to qualified properties

IRI:
Delegation is the assignment of authority and responsibility to an agent (by itself or by another agent) to carry out a specific activity as a delegate or representative, while the agent it acts on behalf of retains some responsibility for the outcome of the delegated work. For example, a student acted on behalf of his supervisor, who acted on behalf of the department chair, who acted on behalf of the university; all those agents are responsible in some way for the activity that took place but we do not say explicitly who bears responsibility and to what degree.
If this Agent prov:actedOnBehalfOf Agent :ag, then it can qualify how with prov:qualifiedResponsibility [ a prov:Responsibility; prov:agent :ag; :foo :bar ].
has super-properties
- prov:qualifiedInfluence op
has domain
has range
qualifies
prov:actedOnBehalfOf op
PROV-DM term
delegation

### (71) Property: prov:influencer op back to qualified properties

IRI:
This property is used as part of the qualified influence pattern. Subclasses of prov:Influence use these subproperties to reference the resource (Entity, Agent, or Activity) whose influence is being qualified.
Subproperties of prov:influencer are used to cite the object of an unqualified PROV-O triple whose predicate is a subproperty of prov:wasInfluencedBy (e.g. prov:used, prov:wasGeneratedBy). prov:influencer is used much like rdf:object is used.
has domain
has range
has sub-properties
PROV-DM term
influence

### (72) Property: prov:entity op back to qualified properties

IRI:
The prov:entity property references an prov:Entity which influenced a resource. This property applies to an prov:EntityInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent.
has super-properties
- prov:influencer op
has domain
has range

### (73) Property: prov:hadUsage op back to qualified properties

IRI:
Usage is the beginning of utilizing an entity by an activity. Before usage, the activity had not begun to utilize this entity and could not have been affected by the entity.
The _optional_ Usage involved in an Entity's Derivation.
has domain
has range
PROV-DM term
Usage

### (74) Property: prov:hadGeneration op back to qualified properties

IRI:
Generation is the completion of production of a new entity by an activity. This entity did not exist before generation and becomes available for usage after this generation.
The _optional_ Generation involved in an Entity's Derivation.
has domain
has range
PROV-DM term
Generation

### (75) Property: prov:activity op back to qualified properties

IRI:
The prov:activity property references an prov:Activity which influenced a resource. This property applies to an prov:ActivityInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent.
has super-properties
- prov:influencer op
has domain
has range

### (76) Property: prov:agent op back to qualified properties

IRI:
The prov:agent property references an prov:Agent which influenced a resource. This property applies to an prov:AgentInfluence, which is given by a subproperty of prov:qualifiedInfluence from the influenced prov:Entity, prov:Activity or prov:Agent.
has super-properties
- prov:influencer op
has domain
has range

### (77) Property: prov:hadPlan op back to qualified properties

IRI:
A plan is an entity that represents a set of actions or steps intended by one or more agents to achieve some goals.
The _optional_ Plan adopted by an Agent in Association with some Activity. Plan specifications are out of the scope of this specification.
has domain
has range
PROV-DM term
Association

### (78) Property: prov:hadActivity op back to qualified properties

IRI:
An activity is something that occurs over a period of time and acts upon or with entities; it may include consuming, processing, transforming, modifying, relocating, using, or generating entities.
The _optional_ Activity of an Influence, which used, generated, invalidated, or was the responsibility of some Entity. This property is _not_ used by ActivityInfluence (use prov:activity instead).
This property has multiple RDFS domains to suit multiple OWL Profiles. See PROV-O OWL Profile.
has domain
- prov:Delegation or prov:Derivation or prov:End or prov:Start
has range
PROV-DM term
Activity

### (79) Property: prov:atTime dp back to qualified properties

IRI:
The PROV data model is implicitly based on a notion of instantaneous events (or just events), that mark transitions in the world. Events include generation, usage, or invalidation of entities, as well as starting or ending of activities. This notion of event is not first-class in the data model, but it is useful for explaining its other concepts and its semantics.
The time at which an InstantaneousEvent occurred, in the form of xsd:dateTime.
has domain
has range
qualifies
prov:invalidatedAtTime dp

### (80) Property: prov:hadRole op back to qualified properties

IRI:
A role is the function of an entity or agent with respect to an activity, in the context of a usage, generation, invalidation, association, start, and end.
The _optional_ Role that an Entity assumed in the context of an Activity. For example, :baking prov:used :spoon; prov:qualified [ a prov:Usage; prov:entity :spoon; prov:hadRole roles:mixing_implement ].
This property has multiple RDFS domains to suit multiple OWL Profiles. See PROV-O OWL Profile.
has domain
- prov:Association or prov:InstantaneousEvent
has range
PROV-DM term
attribute-role

### 4.4 Term Index

The PROV-O terms in this cross reference are shown below alphabetically, along with their entry number.
Table 4: Term Index.
PROV-O Term
Position within Cross Reference
actedOnBehalfOf
Entry 12
Activity
Entry 2
activity
Entry 75
ActivityInfluence
Entry 45
Agent
Entry 3
agent
Entry 76
AgentInfluence
Entry 49
alternateOf
Entry 20
Association
Entry 51
atLocation
Entry 34
atTime
Entry 79
Attribution
Entry 50
Bundle
Entry 15
Collection
Entry 13
Communication
Entry 47
Delegation
Entry 53
Derivation
Entry 41
EmptyCollection
Entry 14
End
Entry 40
endedAtTime
Entry 10
Entity
Entry 1
entity
Entry 72
EntityInfluence
Entry 37
generated
Entry 35
generatedAtTime
Entry 22
Generation
Entry 46
hadActivity
Entry 78
hadGeneration
Entry 74
hadMember
Entry 29
hadPlan
Entry 77
hadPrimarySource
Entry 23
hadRole
Entry 80
hadUsage
Entry 73
Influence
Entry 36
influenced
Entry 33
influencer
Entry 71
InstantaneousEvent
Entry 54
invalidated
Entry 32
invalidatedAtTime
Entry 27
Invalidation
Entry 48
Location
Entry 19
Organization
Entry 18
Person
Entry 16
Plan
Entry 52
PrimarySource
Entry 42
qualifiedAssociation
Entry 68
qualifiedAttribution
Entry 63
qualifiedCommunication
Entry 67
qualifiedDelegation
Entry 70
qualifiedDerivation
Entry 59
qualifiedEnd
Entry 69
qualifiedGeneration
Entry 58
qualifiedInfluence
Entry 57
qualifiedInvalidation
Entry 64
qualifiedPrimarySource
Entry 60
qualifiedQuotation
Entry 61
qualifiedRevision
Entry 62
qualifiedStart
Entry 65
qualifiedUsage
Entry 66
Quotation
Entry 43
Revision
Entry 44
Role
Entry 55
SoftwareAgent
Entry 17
specializationOf
Entry 21
Start
Entry 39
startedAtTime
Entry 7
Usage
Entry 38
used
Entry 8
value
Entry 24
wasAssociatedWith
Entry 11
wasAttributedTo
Entry 6
wasDerivedFrom
Entry 5
wasEndedBy
Entry 31
wasGeneratedBy
Entry 4
wasInfluencedBy
Entry 56
wasInformedBy
Entry 9
wasInvalidatedBy
Entry 28
wasQuotedFrom
Entry 25
wasRevisionOf
Entry 26
wasStartedBy
Entry 30

## A. PROV-O OWL Profile

This section is non-normative.
To encourage widespread adoption, PROV-O's design is intentionally minimal and lightweight. Because the OWL 2 RL profile is aimed at RDF applications that require scalable reasoning without sacrificing too much expressive power [], it served as a baseline for all axioms included in PROV-O. The PROV-O axioms that do not suit the OWL 2 RL profile are listed in Table 5. All five use an anonymous class union for the domain or range of a property, while OWL 2 RL requires the classes to be explicitly named. Although introducing "placeholder" classes would have suited the OWL 2 RL profile, these additional "abstract" classes would have been irrelevant to the modeling of provenance information, increased the size of PROV-O unnecessarily, and exposed a potential to confuse users. All five axioms listed in the following table use a non-superclass expression in a position that requires a superclass expression and do not conform to the OWL 2 RL Profile.
Table 5: All OWL Axioms in PROV-O that do not conform to the OWL-RL profile.
Non OWL-RL PROV-O Axiom
prov:atLocation rdfs:domain [ owl:unionOf (prov:Activity prov:Agent prov:Entity prov:InstantaneousEvent) ]
prov:wasInfluencedBy rdfs:domain [ owl:unionOf (prov:Activity prov:Agent prov:Entity) ]
prov:wasInfluencedBy rdfs:range [ owl:unionOf (prov:Activity prov:Agent prov:Entity) ]
prov:hadActivity rdfs:domain [ owl:unionOf (prov:Delegation prov:Derivation prov:Start prov:End) ]
prov:hadRole rdfs:domain [ owl:unionOf (prov:Association prov:InstantaneousEvent) ]
To provide guidance for OWL 2 RL environments that ignore the union domain axioms, some property domains or ranges have also been defined with the closest common superclass for the classes in the union, as shown in the following table.
Table 6: Intersecting OWL2 RL compatible domains/ranges
Property
Direction
Domain/range
(implied: owl:Thing)
rdfs:domain / rdfs:range
(implied: owl:Thing)
Multiple RDFS domains and ranges [] for a property are interpreted as an intersection, and thus the above do not provide any additional information in an OWL 2 DL or OWL 2 Full profile, which also understands the unions. The more general domain should not be interpreted as saying, e.g., "prov:hadActivity can be used with any prov:Influence", but as "Anything using prov:hadActivity is (at least) a prov:Influence".

## B. Names of inverse properties

To maximize interoperability, PROV-O intentionally avoids defining too many properties' inverses. In fact, it only defines two (prov:generated and prov:invalidated). When all inverses are defined for all properties, modelers may choose from two logically equivalent properties when making each assertion. Although the two options may be logically equivalent, developers consuming the assertions may need to exert extra effort to handle both (e.g., by either adding an OWL reasoner or writing code and queries to handle both cases). This extra effort can be reduced by preferring one inverse over another.
For example, the first PROV-O statement (below) could just as easily be asserted as the second statement. But if a client queries using prov:wasDerivedFrom when :hadDerivation was used in the assertion, no results will be returned unless OWL reasoning is applied (or the size of the query is doubled).
So, PROV-O avoids this situation by encouraging modelers to use one property instead of its inverse; the preferred property to use is the one defined in the PROV-O ontology. Those asserting and querying for the preferred property avoid the need for OWL reasoning, additional code, and larger queries while maintaining the same level of interoperability.
However, the absence of defined inverses can lead to a different risk to interoperability. Because modelers are free to create their own properties to suit their needs, they may be motivated to assert the inverse of any PROV-O property defined herein.
For example, since PROV-O does not define the inverse of prov:wasDerivedFrom, and if three developers would rather model their assertions in the opposite direction, the following set of assertions might be found in the future web of provenance. These assertions are not in an interoperable form without the use of an OWL reasoner, additional code, or larger queries.
To balance these two interoperability risks, this document reserves the names of the PROV-O inverses. The name of a property's inverse is determined by appending the value of its annotation to the PROV namespace ( Modelers wishing to use inverses of the properties defined by PROV-O should use those reserved by this document.
For example, the same three modelers above that defined my:hadDerivation, your:ledTo, and their:derivedTo should instead look for the annotation on prov:wasDerivedFrom to determine that they should use the property
The following table lists the recommended inverse names that should be used if a modeler does not want to use the recommended PROV-O property. For convenience, this file lists the resulting inverse properties.
Table 5: Names of inverses
Domain
PROV-O Property
Recommended inverse name
Range
union
union
union
union
union
union
union

## C. Changes since WD-prov-o-20120724

This section is non-normative.
- Restated prov:hadRole's domain to 'Association or InstantaneousEvent' instead of the original that enumerated the subclasses of InstantaneousEvent ('Association or End or Generation or Invalidation or Start or Usage').
- Renamed prov:Source to prov:PrimarySource and prov:qualifiedSource to prov:qualifiedPrimarySource.
- Examples have been rewritten to avoid usage of TriG named graph syntax except for when showing bundles in prov:asInBundle and prov:mentionOf (since removed to a separate Note). A citation to TriG was added.
- Some examples have been elaborated to use resource names like :illustration_usage rather than :usage_1.
- Fixed naming mismatch by changing prov:hadOriginalSource to prov:hadPrimarySource.
- Rephrased definitions for prov:EntityInfluence, prov:ActivityInfluence, and prov:AgentInfluence to align with the definition of their superclass prov:Influence.
- Updated definitions for prov:Start and prov:End from PROV-DM.
- The property chain for prov:wasInformedBy was fixed from "qualifiedCommunication o entity subproperty of wasInformedBy" to "prov:qualifiedCommunication o prov:activity subproperty of wasInformedBy"
- Removed prov:mentionOf and prov:asInBundle, which have been relocated to its own Note.
- Added comments encouraging the use of the more specific forms of prov:Influence.
- Added uniform references to other "dated" PROV documents.
- Added prefix namespace table.
- Added Compliance with this document section.
- Corrected Turtle syntax for RL violations in PROV-O OWL Profile section. They were missing owl:unionOf.
- Updated attributions for the tools used to produce this document in Acknowledgements section.
- Reworked the Expanded Terms narrative and examples to better highlight each term.

## D. Changes since CR-prov-o-20121211

This section is non-normative.
- Updated exemplar in cross reference entry prov:hadGeneration to include prov:activity property.
- Reordered class and predicate terms from alphabetical to a more natural narrative-based order.
- Added Term Index to aid reading this document in printed form.
- Fixed typo 'iteself' to 'itself'.
- Removed inaccurate property characteristics (AsymmetricProperty, IrreflexiveProperty) in third example of Appendix B.
- Added note to Starting Point Terms stating that rdf:type and rdfs:label are used to express PROV-DM's prov:type and prov:label.
- Updated prov:value's out-of-date definition to conform to PROV-DM's (i.e., "Provides a value that is a direct representation of an entity.".
- Updated prov:wasDerivedFrom's out-of-date definition to conform to PROV-DM's (i.e., "A derivation is a transformation of an entity into another, an update of an entity resulting in a new one, or the construction of a new entity based on a pre-existing entity.".
- Added xsd:dateType datatypes to exemplar in Invalidation and invalidatedAtTime.
- Fixed some incorrect wasAttributedTo/wasAssociatedWith in the cross reference exemplars.
- Changed the status of this document section: added new documents to the PROV Family of Document, and removed the how to read section, referring instead to PROV-OVERVIEW.
- Changed all URLs to PROV documents.

## E. Changes since PR-prov-o-20130312

This section is non-normative.
- Fixed typo in alternateOf example: :london_forecast_043 became :london_forecast_0413
- Changed capitalization in definitions for Organization (new) and Person (new).
