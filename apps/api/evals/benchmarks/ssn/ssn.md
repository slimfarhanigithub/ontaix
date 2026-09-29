## Abstract

The Semantic Sensor Network (SSN) ontology is an ontology for describing sensors and their observations, the involved procedures, the studied features of interest, the samples used to do so, and the observed properties, as well as actuators. SSN follows a horizontal and vertical modularization architecture by including a lightweight but self-contained core ontology called SOSA (Sensor, Observation, Sample, and Actuator) for its elementary classes and properties. With their different scope and different degrees of axiomatization, SSN and SOSA are able to support a wide range of applications and use cases, including satellite imagery, large-scale scientific monitoring, industrial and household infrastructures, social sensing, citizen science, observation-driven ontology engineering, and the Web of Things. Both ontologies are described below, and examples of their usage are given.
The namespace for SSN terms is
The namespace for SOSA terms is
The suggested prefix for the SSN namespace is ssn.
The suggested prefix for the SOSA namespace is sosa.
The SSN ontology is available at
The SOSA ontology is available at

## 1. Introduction

This section is non-normative.
Sensors are a major source of data available on the Web today. While sensor data may be published as mere values, searching, reusing, integrating, and interpreting these data requires more than just the observation results. Of equal importance for the proper interpretation of these values is information about the studied feature of interest, such as a river, the observed property, such as flow velocity, the utilized sampling strategy, such as the specific locations and times at which the velocity was measured, and a variety of other information. OGC's Sensor Web Enablement standards [ ], [] provide a means to annotate sensors and their observations. However, these standards are not integrated and aligned with W3C Semantic Web technologies and Linked Data in particular, which are key drivers for creating and maintaining a global and densely interconnected graph of data. With the rise of the Web of Things and smart cities and homes more generally, actuators and the data they produce also become first-class citizens of the Web. Given their close relation to sensors, observations, procedures, and features of interest, it is desirable to provide a common ontology that also includes actuators and actuation. Finally, with the increasing diversity of data and data providers, definitions such as those for sensors need to be broadened, e.g., to include social sensing. The following specifications introduce the new Semantic Sensor Network (SSN) and Sensor, Observation, Sample, and Actuator (SOSA) ontologies that are set out to provide flexible but coherent perspectives for representing the entities, relations, and activities involved in sensing, sampling, and actuation. SOSA provides a lightweight core for SSN and aims at broadening the target audience and application areas that can make use of Semantic Web ontologies. At the same time, SOSA acts as minimal interoperability fall-back level, i.e., it defines those common classes and properties for which data can be safely exchanged across all uses of SSN, its modules, and SOSA.

## 2. Modularization

This section is non-normative.
Practitioners using the original Semantic Sensor Network Ontology as defined in the W3C Semantic Sensor Network Incubator Group [] have identified a major issue in its complexity, partly due to the layering underneath the Dolce-UltraLite (DUL) upper level ontology. In response to this, the new Semantic Sensor Network (SSN) ontology offers several ontology subsets that are distinguished mainly through their ontological commitments. This section explains the rationale and method for modularizing SSN, i.e., offering several distinct ontologies that are similar in their domain of discourse, but with different ontological commitments, suitable to several use cases and target audiences. For example, SOSA is intended to provide Schema.org-style semantic enrichment capabilities for data repositories managed by an audience broader than typical ontology engineers, while still ensuring interoperability with SSN-based repositories.
Ontology modularization is a common method used in ontology engineering to segment an ontology into smaller parts. In general, ontology modularization aims at providing users of ontologies with the knowledge they require, reducing the scope as much as possible to what is strictly necessary in a given use case. Two main categories of ontology modularization can be distinguished.
The first category comprises those approaches that focus on the composition of existing ontologies by means of integrating and mapping ontologies, most commonly through owl:import statements. OWL import has a direction from a dependent ontology to a dependency ontology. Although import is transitive, knowledge is propagated in only one direction. The importing ontology assumes all the meaning of the imported terms used, by including all axioms relevant to the meaning of these terms. However, the imported ontology does not capture any of the semantics of the importing ontology.
The second category comprises of mapping approaches that aim to partition and extract parts of ontologies as modules. These mapping approaches are not necessarily directional, but most approaches of ontology extraction rely on the directionality of the imported modules. The main feature of an ontology module under the second category is that it is self-contained, i.e., the module captures the meaning of the imported terms used by including all axioms relevant to the meaning of these terms. This means, that the result of certain reasoning tasks such as subsumption or query answering within a single module should be possible and result in the same answers without the need to access other modules of the ontology.
Our modularization uses the first approach by composing the ontology into several modules that use owl:import statements, whereby we distinguish two methods depending on the directionality of the segmentation: a vertical segmentation and a horizontal segmentation.
Figure 1 The SOSA and SSN ontologies and their vertical and horizontal modules.

## Vertical Segmentation

Vertical modules build upon each other, i.e., they directionally owl:import lower level modules. Lower level modules are independent of their higher level modules and logically consistent on their own.
For example, the Dolce-UltraLite Alignment Module imports the SSN Ontology which itself imports the SOSA Ontology. However, in reverse, neither SOSA nor SSN import the Dolce-UltraLite Alignment Module. In fact, SOSA as the core, does not import any other ontologies, which makes it truly independent of vertical modules that add more expressivity and further ontological commitments to the lightweight semantics of SOSA.
Note that higher level here is not to be confused with upper level ontologies. Upper level ontologies are general knowledge ontologies that can be directionally imported in many domains, whereas our definition of higher level ontologies here refers to an ontology that extends one or several ontology modules to capture a larger part of a knowledge domain and/or combine knowledge domains.

## Horizontal Segmentation

Modules that are horizontally layered may depend on each other, i.e., they may rely on the directional import of another horizontal module. Only one horizontal module that is dependent on the SSN ontology is presented in this specification, the Sample Relations Module. Other ontologies that add domain-specific terms to SSN, but require the import of SSN, can be considered horizontal modules.

## 3. Origins of SSN and SOSA

This section is non-normative.
Here we briefly review the origins of SSN and SOSA, namely the initial SSN version published by the W3C Semantic Sensor Network Incubator Group [] and work on Sensor Web Enablement by the OGC. We also highlight the most substantial changes made since the initial release of the SSN ontology.
Starting in 2002, the OGC's Sensor Web Enablement initiative has developed a generic framework for delivering sensor data, dealing with remote-sensing, moving platforms, and in-situ monitoring and sensing. The Sensor Observation Service defines a standard query interface for sensor and observation data, following the pattern established by OGC for their Web Services. The returned XML data conforms with the Sensor Model Language [] and OMXML [], whereby the latter implements Observations and Measurements [].
SensorML and O&M are complementary viewpoints. SensorML is 'provider-centric' and encodes details of the sensor along with raw observation data. SensorML is self-contained and highly flexible. This makes life easy for data producers but is demanding on consumers. SensorML provides extensive support for serialization of numeric data arrays and is particularly optimized for data that includes multiple parallel streams that must be processed together. For example, the data collected by cameras on airborne vehicles must be geo-referenced based on the instantaneous position of the platform and orientation of the camera. In contrast, O&M was designed to be more 'user-centric' with the target of the observation and the observed property as first-class objects. O&M works at a higher semantic level than SensorML, but only provides abstract classes for sensors, features of interest and observable properties, expecting the details to be provided by specific applications and domains. O&M also provided a model for sampling, since almost all scientific observations are made on a subset of, or proxy for, the ultimate feature of interest.
The initial W3C Semantic Sensor Network Incubator Group ontology (SSN) was built around an ontology design pattern called the Stimulus Sensor Observation (SSO) pattern []. The SSO was developed as a minimal and common ground for heavy-weight ontologies for the use on the Semantic Sensor Web as well as to explicitly address the need for light-weight semantics requested by the Linked Data community. The SSO was also aligned to the Dolce-Ultralite upper ontology (DUL).
The new SSN described in this document is based on a revised and expanded version of this pattern, namely the Sensor, Observation, Sample, and Actuator (SOSA) ontology. Similar to the original SSO, SOSA acts as a central building block for the SSN but puts more emphasis on light-weight use and the ability to be used standalone. The axiomatization also changed to provide an experience more related to Schema.org. Notable differences include the usage of the Schema.org domainIncludes and rangeIncludes annotation properties that provide an informal semantics compared to the inferential semantics of their OWL 2 counterparts. In line with the changes implemented for the new SSN, SOSA also drops the direct DUL alignment although an optional alignment can be achieved via the SSN-DUL alignment provided in Section 6.1. SOSA is also more explicit than SSO in its support for virtual and human sensor. Finally, and most notably, SOSA extends SSO's original scope beyond sensors and their observations by including classes and properties for actuators and sampling. SOSA also distinguishes between phenomenonTime and resultTime.
Drawing on considerable implementation and application experience with SSN and sensor and observation ontologies more broadly, the new SSN and SOSA ontologies presented here are set out to address changes in scope and audience, shortcomings of the initial work, as well as new technical developments. The list below highlights the most important (but by far not exclusive) updates.
- Addressing changes in scope and audience
- The initial SSN was developed with ontology engineers in mind as the primary audience. Due to the widespread adoption of SSN, the increasing role of citizen science, the strong focus on lightweight vocabularies by the Linked Data community, and vocabularies such as Schema.org, the ontology was streamlined. SOSA is added as a core, and is also useful as a standalone ontology targeting Web developers, citizen science, lightweight Linked Data publishing, resource-constraint IoT devices, data intensive applications (with the possibility of using lightweight reasoning), and so on. The new SSN introduces additional classes and relations on top of SOSA to model the capabilities of sensors and actuators, the compositionality of systems, and so forth to suit more complex needs or cases in which more provenance data is required, e.g., to improve reproducibility.
- Almost all scientific observations make heavy use of sampling strategies, and, therefore, the Sampling, Sampler, and Sample classes, as well as their corresponding properties, have been added to SOSA and SSN.
- Due to the increasing importance of the Web of Things and smart instrumentation and environments more generally, the classes Actuator and Actuation have been added to SOSA and SSN.
- Addressing shortcomings of the initial SSN
- The new SSN streamlines the relations (and need for) the old Device, Platform, and Systems classes.
- The old SSN was perceived as too heavyweight (on its axiomatization) and too dependent on OWL reasoning by some users. To strike a balance, DL expressivity of the new lightweight SOSA ontology is ALI(D) which is efficiently supported by modern triple stores, while the new SSN is ALRIN(D). In contrast, the old SSN is SRIQ.
- The SSN previously imported DUL and many SSN terms inherited from DUL terms. Due to frequent user requests, this has been redesigned so that SSN (and SOSA) can be used entirely independently of DUL if desired. Some of the alignments with DUL have been reconsidered. Those parts of SSN that use DUL terms have been separated into the SSN Alignment with DUL ontology. This alignment and therefore the role of DUL in SSN have been declared non-normative.
- The definitions for many classes and properties have changed slightly to improve explanation or to correct minor errors. Examples have been separated from the main definitions.
- The initial SSN has been criticized for its partially inconsistent handling of virtual sensors (including software and simulations) and related classes and properties. The new SSN and SOSA address this issue by allowing all major classes to be virtual, and to better support humans and other animals as agents.
- The notion of Procedure (formerly Plan) has been clarified to describe a workflow, protocol, plan, algorithm, or computational method specifying how to make an Observation, create a Sample, or make a change to the state of the world via an Actuator.
- The Observation class in the initial SSN was conceptualized as a subclass of the DUL Situation class. To improve alignment with O&M and user expectations, as well as to follow a consistent modeling strategy for observations, sampling, and actuation, the Observation class defined in SOSA and the new SSN are now conceptualized as activities.
- Addressing technical developments
- The initial SSN used local/guarded domain and range restrictions. The lightweight SOSA ontology uses an even more restrained axiomatization to foster wide reuse and adaptation among an audience that is not necessarily familiar with OWL. SOSA makes use of the domainIncludes and rangeIncludes annotation properties defined in Schema.org. These had not been available before.
- Given the increased interest in using Semantic Web technologies directly on the level of individual sensors, actuators, or platforms, SOSA's axiomatization does not use many of the more complex language elements introduced by SSN.

## 4. Axiomatization

This section introduces the specifications for SOSA and SSN.

### 4.1 Namespaces

The namespace for SSN terms is
The namespace for SOSA terms is
The suggested prefix for the SSN namespace is ssn.
The suggested prefix for the SOSA namespace is sosa.
The SSN ontology is available at
The SOSA ontology is available at

### 4.2 Overview of Classes and Properties

This section is non-normative.
Classes: sosa:ActuatableProperty , sosa:Actuation , sosa:Actuator , ssn:Deployment , sosa:FeatureOfInterest , ssn:Input , sosa:ObservableProperty , sosa:Observation , ssn:Output , sosa:Platform , ssn:Property , sosa:Procedure , sosa:Result , sosa:Sample , sosa:Sampler , sosa:Sampling , sosa:Sensor , ssn:Stimulus , ssn:System
[Show all SOSA and SSN terms] [Show only core SOSA terms]
Object Properties: sosa:actsOnProperty , sosa:madeByActuator , ssn:deployedOnPlatform , ssn:deployedSystem , ssn:detects , ssn:forProperty , ssn:hasDeployment , sosa:hasFeatureOfInterest , ssn:hasInput , ssn:hasOutput , ssn:hasProperty , sosa:hasResult , sosa:hasSample , ssn:hasSubSystem , sosa:hosts , ssn:implementedBy , ssn:implements , ssn:inDeployment , sosa:isActedOnBy , sosa:isFeatureOfInterestOf , sosa:isHostedBy , sosa:isObservedBy , ssn:isPropertyOf , ssn:isProxyFor , sosa:isResultOf , sosa:isSampleOf , sosa:madeActuation , sosa:madeBySampler , sosa:madeBySensor , sosa:madeObservation , sosa:madeSampling , sosa:observedProperty , sosa:observes , sosa:phenomenonTime , sosa:usedProcedure , ssn:wasOriginatedBy
[Show all SOSA and SSN terms] [Show only core SOSA terms]
Datatype Properties: sosa:hasSimpleResult , sosa:resultTime
Several conceptual modules have been defined to cover key sensor, actuation and sampling concepts. The different conceptual modules of SOSA/SSN can be seen in the following figure.
Figure 2 Overview of the SOSA/SSN ontology modules
An overview of the main classes and properties inside the ontology modules can be seen in the following figures, from the perspectives of Observation, Actuation and Sampling. In the figures, and in the rest of the document, SOSA-related components and restrictions are shown in green, while SSN-only components are shown in blue.
Figure 3 Overview of the SOSA classes and properties (observation perspective)
Figure 4 Overview of the SSN classes and properties (observation perspective)
Figure 5 Overview of the SOSA classes and properties (actuation perspective)
Figure 6 Overview of the SSN classes and properties (actuation perspective)
Figure 7 Overview of the SOSA classes and properties (sampling perspective)
Figure 8 Overview of the SSN classes and properties (sampling perspective)

### 4.3 Observations

#### 4.3.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are specifically related to modeling Observations. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
[Show all SOSA and SSN terms] [Show only core SOSA terms]
Figure 9 Classes and relationships involved in Observation (SOSA)
Figure 10 Classes and relationships involved in Observation (SOSA/SSN)
The following examples illustrate how the terms related to Observation can be used:
- iPhone Barometer
- Coal Oil Point Reserve
- Apartment 134
- Tree height measurement
- Number of sunspots
- Seismographs
- Wind sensor spinning cups
- IP68 Smart Sensor

#### 4.3.2 Specification

This section introduces the following classes and properties:
[Show all SOSA and SSN terms] [Show only core SOSA terms]

##### 4.3.2.1 sosa:ObservableProperty

IRI:
a OWL Class
Observable Property - An observable quality (property, characteristic) of a FeatureOfInterest.
The height of a tree, the depth of a water body, or the temperature of a surface are examples of observable properties, while the value of a classic car is not (directly) observable but asserted.
Sub class of
Restrictions
sosa:isObservedBy ONLY sosa:Sensor
inverse Of sosa:observedProperty ONLY sosa:Observation
inverse Of ssn:isProxyFor ONLY ssn:Stimulus
is Defined By
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.3.2.2 sosa:Observation

IRI:
a OWL Class
Observation - Act of carrying out an (Observation) Procedure to estimate or calculate a value of a property of a FeatureOfInterest. Links to a Sensor to describe what made the Observation and how; links to an ObservableProperty to describe what the result is an estimate of, and to a FeatureOfInterest to detail what that property was associated with.
The activity of estimating the intensity of an Earthquake using the Mercalli intensity scale is an Observation as is measuring the moment magnitude, i.e., the energy released by said earthquake.
Restrictions
sosa:madeBySensor EXACTLY 1
sosa:madeBySensor ONLY sosa:Sensor
sosa:usedProcedure ONLY sosa:Procedure
sosa:hasFeatureOfInterest EXACTLY 1
sosa:hasFeatureOfInterest ONLY sosa:FeatureOfInterest
sosa:observedProperty EXACTLY 1
sosa:observedProperty ONLY sosa:ObservableProperty
ssn:wasOriginatedBy EXACTLY 1
ssn:wasOriginatedBy ONLY ssn:Stimulus
sosa:phenomenonTime EXACTLY 1
sosa:hasResult MIN 1
sosa:hasResult ONLY sosa:Result
sosa:resultTime EXACTLY 1
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.3.2.3 sosa:observedProperty

IRI:
a OWL Object Property
observed property - Relation linking an Observation to the property that was observed. The ObservableProperty should be a property of the FeatureOfInterest (linked by hasFeatureOfInterest) of this Observation.
Domain Includes
Range Includes
[Back to module overview and examples] [Back to top]

##### 4.3.2.4 sosa:phenomenonTime

IRI:
a OWL Object Property
phenomenon time - The time that the Result of an Observation, Actuation, or Sampling applies to the FeatureOfInterest. Not necessarily the same as the resultTime. May be an interval or an instant, or some other compound temporal entity [].
Domain Includes
Range Includes
[Back to module overview and examples] [Back to top]

##### 4.3.2.5 sosa:Sensor

IRI:
a OWL Class
Sensor - Device, agent (including humans), or software (simulation) involved in, or implementing, a Procedure. Sensors respond to a Stimulus, e.g., a change in the environment, or Input data composed from the Results of prior Observations, and generate a Result. Sensors can be hosted by Platforms.
Accelerometers, gyroscopes, barometers, magnetometers, and so forth are Sensors that are typically mounted on a modern smart phone (which acts as Platform). Other examples of Sensors include the human eyes.
Sub class of
Restrictions
ssn:implements MIN 1
sosa:observes ONLY sosa:ObservableProperty
ssn:detects ONLY ssn:Stimulus
sosa:madeObservation ONLY sosa:Observation
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.3.2.6 sosa:observes

IRI:
a OWL Object Property
observes - Relation between a Sensor and an ObservableProperty that it is capable of sensing.
Domain Includes
Range Includes
Inverse property of
Sub property of
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.3.2.7 sosa:isObservedBy

IRI:
a OWL Object Property
is observed by - Relation between an ObservableProperty and the Sensor able to observe it.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.3.2.8 sosa:madeObservation

IRI:
a OWL Object Property
made observation - Relation between a Sensor and an Observation made by the Sensor.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.3.2.9 sosa:madeBySensor

IRI:
a OWL Object Property
made by Sensor - Relation between an Observation and the Sensor which made the Observations.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.3.2.10 ssn:Stimulus

IRI:
a OWL Class
Stimulus - An event in the real world that 'triggers' the Sensor. The properties associated to the Stimulus may be different to the eventual observed ObservableProperty. It is the event, not the object, that triggers the Sensor.
Restrictions
ssn:isProxyFor ONLY sosa:ObservableProperty
inverse Of ssn:wasOriginatedBy ONLY sosa:Observation
inverse Of ssn:detects ONLY sosa:Sensor
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.3.2.11 ssn:isProxyFor

IRI:
a OWL Object Property
isProxyFor - A relation from a Stimulus to the Property that the Stimulus is serving as a proxy for.
For example, the expansion of quicksilver is a Stimulus that serves as a proxy for some temperature Property. An increase or decrease in the velocity of spinning cups on a wind Sensor is serving as a proxy for the wind speed.
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.3.2.12 ssn:wasOriginatedBy

IRI:
a OWL Object Property
was originated by - Relation between an Observation and the Stimulus that originated it.
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.3.2.13 ssn:detects

IRI:
a OWL Object Property
detects - A relation from a Sensor to the Stimulus that the Sensor detects. The Stimulus itself will be serving as a proxy (isProxyFor) for some ObservableProperty.
is Defined By
[Back to module overview and examples] [Back to top]

### 4.4 Actuations

#### 4.4.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling Actuations. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
[Show all SOSA and SSN terms] [Show only core SOSA terms]
Figure 11 Classes and relationships involved in Actuation (SOSA)
Figure 12 Classes and relationships involved in Actuation (SOSA/SSN)
The following example illustrate how the terms related to Actuations can be used:
- apartment 134

#### 4.4.2 Specification

This section introduces the following classes and properties:

##### 4.4.2.1 sosa:ActuatableProperty

IRI:
a OWL Class
Actuatable Property - An actuatable quality (property, characteristic) of a FeatureOfInterest.
A window actuator acts by changing the state between a frame and a window. The ability of the window to be opened and closed is its ActuatableProperty.
Sub class of
Restriction
sosa:isActedOnBy ONLY sosa:Actuation
is Defined By
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.4.2.2 sosa:Actuation

IRI:
a OWL Class
Actuation - An Actuation carries out an (Actuation) Procedure to change the state of the world using an Actuator.
The activity of automatically closing a window if the temperature in a room drops below 20 degree Celsius. The activity is the Actuation and the device that closes the window is the Actuator. The Procedure is the rule, plan, or specification that defines the Conditions that triggers the Actuation, here a drop in temperature.
Restrictions
sosa:madeByActuator EXACTLY 1
sosa:madeByActuator ONLY sosa:Actuator
sosa:usedProcedure ONLY sosa:Procedure
sosa:hasFeatureOfInterest EXACTLY 1
sosa:hasFeatureOfInterest ONLY sosa:FeatureOfInterest
sosa:actsOnProperty MIN 1
sosa:actsOnProperty ONLY sosa:ActuatableProperty
sosa:hasResult MIN 1
sosa:hasResult ONLY sosa:Result
sosa:resultTime EXACTLY 1
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.4.2.3 sosa:actsOnProperty

IRI:
a OWL Object Property
acts on property - Relation between an Actuation and the property of a FeatureOfInterest it is acting upon.
In the activity (Actuation) of automatically closing a window if the temperature in a room drops below 20 degrees Celsius, the property on which the Actuator acts upon is the state of the window as it changes from being open to being closed.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.4.2.4 sosa:isActedOnBy

IRI:
a OWL Object Property
is acted on by - Relation between an ActuatableProperty of a FeatureOfInterest and an Actuation changing its state.
In the activity (Actuation) of automatically closing a window if the temperature in a room drops below 20 degrees Celsius, the property on which the Actuator acts upon is the state of the window as it changes from being open to being closed.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.4.2.5 sosa:Actuator

IRI:
a OWL Class
Actuator - A device that is used by, or implements, an (Actuation) Procedure that changes the state of the world.
A window actuator for automatic window control, i.e., opening or closing the window.
Sub class of
Restrictions
ssn:implements MIN 1
ssn:forProperty ONLY sosa:ActuatableProperty
sosa:madeActuation ONLY sosa:Actuation
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.4.2.6 sosa:madeActuation

IRI:
a OWL Object Property
made actuation - Relation between an Actuator and the Actuation made by the Actuator.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.4.2.7 sosa:madeByActuator

IRI:
a OWL Object Property
made by actuator - Relation linking an Actuation to the Actuator that made that Actuation.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

### 4.5 Samplings

#### 4.5.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling Samplings. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
[Show all SOSA and SSN terms] [Show only core SOSA terms]
Figure 13 Classes and relationships involved in Sampling (SOSA)
Figure 14 Classes and relationships involved in Sampling (SOSA/SSN)
The following examples illustrate how the terms related to Samplings can be used:
- iPhone Barometer
- Coal Oil Point Reserve
- Seismographs
- Ice Core
- DHT22 Deployment
- IP68 Smart Sensor

#### 4.5.2 Specification

This section introduces the following classes and properties:

##### 4.5.2.1 sosa:Sample

IRI:
a OWL Class
Sample - Feature which is intended to be representative of a FeatureOfInterest on which Observations may be made.
Comment
Samples are typically subsets or extracts from the feature of interest of an observation. They are used in situations where observations cannot be made directly on the ultimate feature of interest, either because the entire feature cannot be observed, or because it is more convenient to use a proxy. Samples are thus artifacts of an observational strategy, and usually have no significant function outside of their role in the observation process. The characteristics of the samples themselves are generally of little interest, except to the manager of a sampling campaign, or sample curator.
A Sample is intended to sample some FeatureOfInterest, so there is an expectation of at least one isSampleOf property. However, in some cases the identity, and even the exact type, of the sampled feature may not be known when observations are made using the sampling features.
Physical samples are sometimes known as 'specimens'.
A 'station' is essentially an identifiable locality where a Sensor system or procedure may be deployed and an observation made. In the context of the observation model, it connotes the 'world in the vicinity of the station', so the observed properties relate to the physical medium at the station, and not to any physical artifact such as a mooring, buoy, benchmark, monument, well, etc.
A statistical sample is often designed to be characteristic of an entire population, so that Observations can be made regarding the sample that provide a good estimate of the properties of the population.
Sub class of
Restrictions
sosa:isResultOf ONLY sosa:Sampling
sosa:isResultOf MIN 1 sosa:Sampling
sosa:isSampleOf ONLY sosa:FeatureOfInterest
sosa:isSampleOf MIN 1
is Defined By
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.5.2.2 sosa:hasSample

IRI:
a OWL Object Property
has sample - Relation between a FeatureOfInterest and the Sample used to represent it.
Domain Includes
Range Includes
Inverse property of
is Inverse-Functional
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.5.2.3 sosa:isSampleOf

IRI:
a OWL Object Property
is sample of - Relation from a Sample to the FeatureOfInterest that it is intended to be representative of.
Domain Includes
Range Includes
Inverse property of
is Functional
[Back to module overview and examples] [Back to top]

##### 4.5.2.4 sosa:Sampling

IRI:
a OWL Class
Sampling - An act of Sampling carries out a (Sampling) Procedure to create or transform one or more Samples.
Crushing a rock sample in a ball mill.
Digging a pit through a soil sequence.
Dividing a field site into quadrants.
Drawing blood from a patient.
Drilling an observation well.
Establishing a station for environmental monitoring.
Registering an image of the landscape.
Sieving a powder to separate the subset finer than 100-mesh.
Selecting a subset of a population.
Splitting a piece of drill-core to create two new samples.
Taking a diamond-drill core from a rock outcrop.
Restrictions
sosa:madeBySampler EXACTLY 1
sosa:madeBySampler ONLY sosa:Sampler
sosa:usedProcedure ONLY sosa:Procedure
sosa:hasFeatureOfInterest EXACTLY 1
sosa:hasFeatureOfInterest ONLY sosa:FeatureOfInterest
sosa:hasResult MIN 1 sosa:Sample
sosa:hasResult ONLY sosa:Sample
sosa:resultTime EXACTLY 1
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.5.2.5 sosa:Sampler

IRI:
a OWL Class
Sampler - A device that is used by, or implements, a (Sampling) Procedure to create or transform one or more samples.
A ball mill, diamond drill, hammer, hypodermic syringe and needle, image Sensor or a soil auger can all act as sampling devices (i.e., be Samplers). However, sometimes the distinction between the Sampler and the Sensor is not evident, as they are packaged as a unit. A Sampler need not be a physical device.
Sub class of
Restrictions
ssn:implements MIN 1
sosa:madeSampling ONLY sosa:Sampling
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.5.2.6 sosa:madeSampling

IRI:
a OWL Object Property
made sampling - Relation between a Sampler (sampling device or entity) and the Sampling act it performed.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.5.2.7 sosa:madeBySampler

IRI:
a OWL Object Property
made by sampler - Relation linking an act of Sampling to the Sampler (sampling device or entity) that made it.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

### 4.6 Features of Interest and Properties

#### 4.6.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling Features of Interest and Properties. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
Figure 15 Classes and relationships related to features of interest and properties
The following examples illustrate how the terms related to Features of Interest and Properties can be used:
- iPhone Barometer
- Coal Oil Point Reserve
- apartment 134
- Tree height measurement
- Seismographs
- Number of sunspots
- Wind sensor spinning cups
- Ice Core
- DHT22 Deployment
- IP68 Smart Sensor

#### 4.6.2 Specification

This section introduces the following classes and properties:
[Show all SOSA and SSN terms] [Show only core SOSA terms]

##### 4.6.2.1 sosa:FeatureOfInterest

IRI:
a OWL Class
Feature Of Interest - The thing whose property is being estimated or calculated in the course of an Observation to arrive at a Result, or whose property is being manipulated by an Actuator, or which is being sampled or transformed in an act of Sampling.
When measuring the height of a tree, the height is the observed ObservableProperty, 20m may be the Result of the Observation, and the tree is the FeatureOfInterest. A window is a FeatureOfInterest for an automatic window control Actuator.
Restrictions
ssn:hasProperty ONLY ssn:Property
ssn:hasProperty MIN 1
sosa:hasSample ONLY sosa:Sample
is Defined By
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.6.2.2 sosa:hasFeatureOfInterest

IRI:
a OWL Object Property
has feature of interest - A relation between an Observation and the entity whose quality was observed, or between an Actuation and the entity whose property was modified, or between an act of Sampling and the entity that was sampled.
For example, in an Observation of the weight of a person, the FeatureOfInterest is the person and the property is its weight.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.6.2.3 sosa:isFeatureOfInterestOf

IRI:
a OWL Object Property
is feature of interest of - A relation between a FeatureOfInterest and an Observation about it or an Actuation acting on it, or an act of Sampling that sampled it.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.6.2.4 ssn:Property

IRI:
a OWL Class
Property - A quality of an entity. An aspect of an entity that is intrinsic to and cannot exist without the entity.
Restrictions:
ssn:isPropertyOf ONLY sosa:FeatureOfInterest
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.6.2.5 ssn:hasProperty

IRI:
a OWL Object Property
has property - Relation between an entity and a Property of that entity.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.6.2.6 ssn:isPropertyOf

IRI:
a OWL Object Property
is property of - Relation between a Property and the entity it belongs to.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.6.2.7 ssn:forProperty

IRI:
a OWL Object Property
for property - A relation between some aspect of an entity and a Property.
For example, from a Sensor to the properties it can observe; from an Actuator to the properties it can act on; from a Deployment to the properties it was installed to observe or act on; from a SystemCapability to the Property the capability is described for.
is Defined By
[Back to module overview and examples] [Back to top]

### 4.7 Results

#### 4.7.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling Results. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
Figure 16 Classes and relationships related to results
The following examples illustrate how the terms related to Results can be used:
- iPhone Barometer
- Coal Oil Point Reserve
- apartment 134
- Tree height measurement
- Seismographs
- Number of sunspots
- Wind sensor spinning cups
- Ice Core
- IP68 Smart Sensor

#### 4.7.2 Specification

This section introduces the following classes and properties:

##### 4.7.2.1 sosa:Result

IRI:
a OWL Class
Result - The Result of an Observation, Actuation, or act of Sampling. To store an observation's simple result value one can use the hasSimpleResult property.
The value 20 as the height of a certain tree together with the unit, e.g., Meter.
Restriction
sosa:isResultOf MIN 1
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.7.2.2 sosa:hasResult

IRI:
a OWL Object Property
has result - Relation linking an Observation and a Sensor or Actuator and a Result, which contains a value representing the value associated with the observed Property.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.7.2.3 sosa:isResultOf

IRI:
a OWL Object Property
is result of - Relation linking a Result to the Observation or Actuation that created or caused it.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.7.2.4 sosa:hasSimpleResult

IRI:
a OWL Datatype Property
has simple result - The simple value of an Observation or Actuation.
For instance, the values 23 or true.
Domain Includes
[Back to module overview and examples] [Back to top]

##### 4.7.2.5 sosa:resultTime

IRI:
a OWL Datatype Property
result time - The result time is the instant of time when the Observation, Actuation or Sampling activity was completed.
Domain Includes
Range
[Back to module overview and examples] [Back to top]

### 4.8 Procedures

#### 4.8.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling Procedures. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
Figure 17 Classes and relationships related to procedures
The following examples illustrate how the terms related to Procedures can be used:
- DHT22 Description
- IP68 Smart Sensor

#### 4.8.2 Specification

This section introduces the following classes and properties:
sosa:Procedure, sosa:usedProcedure, ssn:implements, ssn:implementedBy, ssn:hasInput, ssn:hasOutput, ssn:Input, ssn:Output,
[Show all SOSA and SSN terms] [Show only core SOSA terms]

##### 4.8.2.1 sosa:Procedure

IRI:
a OWL Class
Procedure - A workflow, protocol, plan, algorithm, or computational method specifying how to make an Observation, create a Sample, or make a change to the state of the world (via an Actuator). A Procedure is re-usable, and might be involved in many Observations, Samplings, or Actuations. It explains the steps to be carried out to arrive at reproducible Results.
The measured wind speed differs depending on the height of the Sensor above the surface, e.g., due to friction. Consequently, procedures for measuring wind speed define a standard height for anemometers above ground, typically 10m for meteorological measures and 2m in Agrometeorology. This definition of height, Sensor placement, and so forth are defined by the Procedure.
Note
Many Observations may be created via the same Procedure, the same way as many tables are assembled using the same instructions (as information objects, not their concrete realization).
Restrictions
ssn:hasInput ONLY ssn:Input
ssn:hasOutput ONLY ssn:Output
ssn:implementedBy ONLY ssn:System
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.8.2.2 sosa:usedProcedure

IRI:
a OWL Object Property
used procedure - A relation to link to a re-usable Procedure used in making an Observation, an Actuation, or a Sample, typically through a Sensor, Actuator or Sampler.
Domain Includes
Range Includes
Sub property of Chain
sosa:madeBySensor o ssn:implements
sosa:madeByActuator o ssn:implements
sosa:madeBySampler o ssn:implements
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.8.2.3 ssn:implements

IRI:
a OWL Object Property
implements - Relation between an entity that implements a Procedure in some executable way and the Procedure (an algorithm, procedure or method).
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.8.2.4 ssn:implementedBy

IRI:
a OWL Object Property
implemented by - Relation between a Procedure (an algorithm, procedure or method) and an entity that implements that Procedure in some executable way.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.8.2.5 ssn:hasInput

IRI:
a OWL Object Property
has Input - Relation between a Procedure and an Input to it.
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.8.2.6 ssn:Input

IRI:
a OWL Class
Input - Any information that is provided to a Procedure for its use.
Restrictions
inverse Of ssn:hasInput ONLY sosa:Procedure
inverse Of ssn:hasInput MIN 1
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.8.2.7 ssn:hasOutput

IRI:
a OWL Object Property
has Output - Relation between a Procedure and an Output of it.
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.8.2.8 ssn:Output

IRI:
a OWL Class
Output - Any information that is reported from a Procedure.
Restrictions
inverse Of ssn:hasOutput ONLY sosa:Procedure
inverse Of ssn:hasOutput MIN 1
is Defined By
[Back to module overview and examples] [Back to top]

### 4.9 Systems and their Deployment

#### 4.9.1 Overview and examples

This section is non-normative.
The following figure provides an overview of the core classes and properties that are secifically related to modeling systems and their deployment. SOSA axioms are shown in green, while SSN-only axioms are shown in blue.
Figure 18 Classes and relationships related to systems and deployments
The following examples illustrate how the terms related to Systems and their Deployment can be used:
- DHT22 Description
- DHT22 Deployment

#### 4.9.2 Specification

This section introduces the following classes and properties:
[Show all SOSA and SSN terms] [Show only core SOSA terms]

##### 4.9.2.1 sosa:Platform

IRI:
a OWL Class
Platform - A Platform is an entity that hosts other entities, particularly Sensors, Actuators, Samplers, and other Platforms.
A post, buoy, vehicle, ship, aircraft, satellite, cell-phone, human or animal may act as Platforms for (technical or biological) Sensors or Actuators.
Restrictions
sosa:hosts ONLY ssn:System
ssn:inDeployment ONLY ssn:Deployment
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.9.2.2 sosa:hosts

IRI:
a OWL Object Property
hosts - Relation between a Platform and a Sensor, Actuator, Sampler, or Platform, hosted or mounted on it.
Domain Includes
Range Includes
Inverse property of
Sub property of Chain
ssn:inDeployment o ssn:deployedSystem
[Show additional SSN axioms] [Hide additional SSN axioms] [Back to module overview and examples] [Back to top]

##### 4.9.2.3 sosa:isHostedBy

IRI:
a OWL Object Property
is hosted by - Relation between a Sensor, or Actuator, Sampler, or Platform, and the Platform that it is mounted on or hosted by.
Domain Includes
Range Includes
Inverse property of
[Back to module overview and examples] [Back to top]

##### 4.9.2.4 ssn:System

IRI:
a OWL Class
System - System is a unit of abstraction for pieces of infrastructure that implement Procedures. A System may have components, its subsystems, which are other Systems.
Restrictions
sosa:isHostedBy ONLY sosa:Platform
ssn:implements ONLY sosa:Procedure
ssn:hasSubSystem ONLY ssn:System
inverse Of ssn:hasSubSystem ONLY ssn:System
ssn:hasDeployment ONLY ssn:Deployment
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.5 ssn:hasSubSystem

IRI:
a OWL Object Property
has subsystem - Relation between a System and its component parts.
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.6 ssn:Deployment

IRI:
a OWL Class
Deployment - Describes the Deployment of one or more Systems for a particular purpose. Deployment may be done on a Platform.
For example, a temperature Sensor deployed on a wall, or a whole network of Sensors deployed for an Observation campaign.
Restrictions
ssn:deployedSystem ONLY ssn:System
ssn:deployedOnPlatform ONLY sosa:Platform
ssn:forProperty ONLY ssn:Property
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.7 ssn:deployedSystem

IRI:
a OWL Object Property
deployed system - Relation between a Deployment and a deployed System.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.8 ssn:hasDeployment

IRI:
a OWL Object Property
has deployment - Relation between a System and a Deployment, recording that the System is deployed in that Deployment.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.9 ssn:deployedOnPlatform

IRI:
a OWL Object Property
deployed on platform - Relation between a Deployment and the Platform on which the Systems are deployed.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

##### 4.9.2.10 ssn:inDeployment

IRI:
a OWL Object Property
in deployment - Relation between a Platform and a Deployment, meaning that the deployedSystems of the Deployment are hosted on the Platform.
For example, a relation between a buoy and a Deployment of several Sensors.
Inverse property of
is Defined By
[Back to module overview and examples] [Back to top]

