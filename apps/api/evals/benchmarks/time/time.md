## Abstract

OWL-Time is an OWL-2 DL ontology of temporal concepts, for describing the temporal properties of resources in the world or described in Web pages. The ontology provides a vocabulary for expressing facts about topological (ordering) relations among instants and intervals, together with information about durations, and about temporal position including date-time information. Time positions and durations may be expressed using either the conventional (Gregorian) calendar and clock, or using another temporal reference system such as Unix-time, geologic time, or different calendars.
The namespace for OWL-Time terms is
The suggested prefix for the OWL-Time namespace is time
The OWL-Time ontology is available here.
An ontology of individuals for the Gregorian calendar (months) is available here.

## 1. Motivation and background

Temporal information is important in most real world applications. For example, the date is always part of an online order. When you rent a car it is for specific dates. Events in the world occur at specific times and usually have a finite duration. Transactions occur in a sequence, with the current state of a system depending on the exact history of all the transactions. Knowledge of the temporal relationships between transactions, events, travel and orders is often critical. OWL-Time has been developed in response to this need, for describing the temporal properties of any resource denoted using a web identifier (URI), including web-pages and real-world things if desired. It focusses particularly on temporal ordering relationships. While these are implicit in all temporal descriptions, OWL-Time provides specific predicates to support, or to make explicit the results of, reasoning over the order or sequence of temporal entities.
There is a great deal of relevant existing work, some very closely related. ISO 8601 [] provides a basis for encoding time position and extent in a character string, using the most common modern calendar-clock system. Datatypes in XML Schema [] use a subset of the ISO 8601 format in order to pack multi-element values into a compact literal. Functions and operators on durations, and on dates and times, encoded in these ways are available in XPath and XQuery []. XSLT [] also provides formatting functions for times and dates, with explicit support for the specified language, calendar and country. Some of the XML Schema datatypes are built-in to OWL2 [], so the XPath and XQuery functions may be used on basic OWL data.
OWL-Time makes use of these encodings, but also provides representations in which the elements of a date and time are put into separately addressable resources, which can help with queries and reasoning applications. OWL-Time also supports other representations of temporal position and duration, including temporal coordinates (scaled position on a continuous temporal axis) and ordinal times (named positions or periods), as well as relaxing the expectation from the original version that dates must use the Gregorian calendar. However, OWL-Time has a particular focus on ordering relations ("temporal topology"), which is not supported explicitly in any of the date-time encodings.
A first-order logic axiomatization of the core of this ontology is available in []. This document presents the OWL encodings of the ontology, with some additions.
This version of OWL-Time was developed in the Spatial Data on the Web Working Group (a joint activity involving W3C and the Open Geospatial Consortium). The ontology is based on the draft by Hobbs and Pan [], incorporating modifications proposed by Cox [] to support more general temporal positions, along with other minor improvements. The substantial changes are listed in the change-log. The specification document has been completely re-written.

## 2. Notation and namespaces

Classes and properties from the Time Ontology are denoted in this specification using Compact URIs [].
The namespace for OWL-Time is OWL-Time does not re-use elements from any other vocabularies, but does use some built-in datatypes from OWL and some additional types from XML Schema Part 2.
The table below indicates the full list of namespaces and prefixes used in this document.
Prefix
Namespace
ex
geol
greg
owl
prov
rdf
rdfs
time or
no prefix
xsd
Where class descriptions include local restrictions on properties, these are described using the OWL 2 Manchester Syntax [].
Examples and other code fragments are serialized using RDF 1.1 Turtle notation [].

## 3. Principles and vocabulary overview

This section is non-normative.

### 3.1 Topological Temporal Relations

The basic structure of the ontology is based on an algebra of binary relations on intervals (e.g., meets, overlaps, during) developed by Allen [], [] for representing qualitative temporal information, and to address the problem of reasoning about such information.
The ontology starts with a class :TemporalEntity with properties :hasBeginning and :hasEnd that link to the temporal instants that define its limits, and :hasTemporalDuration to describe its extent. There are two subclasses: :Interval and :Instant, and they are the only two subclasses of :TemporalEntity. Intervals are, intuitively, things with extent. Instants are, intuitively, point-like in that they have no interior points, but it is generally safe to think of an instant as an interval with zero length, where the beginning and end are the same.
This idea - that time intervals are the more general case and time instants are just a limited specialization - is the first key contribution of Allen's analysis.
The class :Interval has one subclass :ProperInterval, which corresponds with the common understanding of intervals, in that the beginning and end are distinct, and whose membership is therefore disjoint from :Instant.
Figure 1 Core model of temporal entities.
The class :ProperInterval also has one subclass, :DateTimeInterval. The position and extent of a :DateTimeInterval is an element in a :GeneralDateTimeDescription.
Relations between intervals are the critical logic provided by Allen's analysis, and implemented in the ontology. These can be defined in a relatively straightforward fashion in terms of :before and identity on the beginning and end points. The thirteen elementary relations shown below are the second key contribution of Allen's analysis. These support unambiguous expression of all possible relations between temporal entities, which allows the computation of any relative position or sequence. Note that the standard interval calculus assumes all intervals are proper, so their beginning and end are different.
Figure 2 Thirteen elementary possible relations between time periods [].
Two additional relations: In (the union of During, Starts and Finishes) and Disjoint (the union of Before and After) are not shown in the figure but are included in the ontology.
The properties :hasTemporalDuration, :hasBeginning and :hasEnd, together with a fourth generic property :hasTime, support the association of temporal information with any temporal entity, such as an activity or event, or other entity. These provide a standard way to attach time information to things, which may be used directly in applications if suitable, or specialized if needed.

### 3.2 Temporal reference systems, clocks, calendars

The duration of a TemporalEntity may be given using the datatype xsd:duration and the position of an Instant may be given using the datatype xsd:dateTimeStamp, which is built in to OWL 2 []. These both use the conventional notions of temporal periods (years, months, weeks ... seconds), the Gregorian calendar, and the 24-hour clock. The lexical representations use [] style notation, but ignoring leap seconds, which are explicitly mandated by the international standard.
While this satisfies most web applications, many other calendars and temporal reference systems are used in particular cultural and scholarly contexts. For example, the Julian calendar was used throughout Europe until the 16th century, and is still used for computing key dates in some orthodox Christian communities. Lunisolar (e.g. Hebrew) and lunar (e.g. Islamic) calendars are currently in use in some communities, and many similar have been used historically. Ancient Chinese calendars as well as the French revolutionary calendar used 10-day weeks. In scientific and technical applications, Julian date counts the number of days since the beginning of 4713 BCE, and Loran-C, Unix and GPS time are based on seconds counted from a specified origin in 1958, 1970 and 1980, respectively, with GPS time represented using a pair of numbers for week number plus seconds into week. Archaeological and geological applications use chronometric scales based on years counted backwards from ‘the present’ (defined as 1950 for radiocarbon dating []), or using named periods associated with specified correlation markers ([], [], []). Dynastic calendars (counting years within eras defined by the reign of a monarch or dynasty) were used in many cultures. In order to support these more general applications, the representation of temporal position and duration must be flexible, and annotated with the temporal reference system in use.
A set of ordered intervals (e.g. named dynasties, geological periods, geomagnetic reversals, tree rings) can make a simple form of temporal reference system that supports logical reasoning, known as an ordinal temporal reference system [].
Measurement of duration needs a clock. In its most general form a clock is just a regularly repeating physical event ('tick') and a counting mechanism for the 'ticks'. These counts may be used to logically relate two events and to calculate a duration between the events.
A calendar is a set of algorithms that enables clock counts to be converted into practical everyday dates and times related to the movement of astronomical bodies (day, month, year).
Note
As astronomically based calendars try to fit inconvenient durations into a usable regular system of counting cycles, 'intercalations' are often used to re-align the calendar's repeating patterns with astronomical events. These intercalations may be of different durations depending on the calendar, such as leap seconds, leap days, or even a group of days. Leap days are explicit and leap seconds implicit in the Gregorian calendar, which underlies the model used in several classes in OWL-Time. A general treatment of intercalations is beyond the scope of this ontology.
For many purposes it is convenient to make temporal calculations in terms of clock durations that exceed everyday units such as days, weeks, months and years, using a representation of temporal position in a temporal coordinate system [], i.e. on a number line with a specified origin, such as Julian date, or Unix time. This may be converted to calendar units when necessary for human consumption.
Nevertheless, in practice much temporal information is not well-defined, in that there may be no clear statement about the assumed underlying calendar and clock.

### 3.3 Time position

OWL 2 has two built-in datatypes relating to time: xsd:dateTime and xsd:dateTimeStamp []. Other XSD types such as xsd:date, xsd:gYear and xsd:gYearMonth [] are also commonly used in OWL applications. These provide for a compact representation of time positions using the conventional Gregorian calendar and 24-hour clock, with timezone offset from UTC.
Four classes in the ontology support an explicit description of temporal position. :TemporalPosition is the common super-class, with a property :hasTRS to indicate the temporal reference system in use. :TimePosition has properties to alternatively describe the position using a number (i.e. a temporal coordinate), or a nominal value (e.g. geologic time period, dynastic name, archeological era). :GeneralDateTimeDescription has a set of properties to specify a date-time using calendar and clock elements. Its subclass :DateTimeDescription fixes the temporal reference system to the Gregorian calendar.
Figure 3 Classes for temporal position.
Following Allen's first key idea described above, even a time position has a finite extent, corresponding to the precision or temporal unit used. Thus, a :GeneralDateTimeDescription or :DateTimeDescription has a duration corresponding to the value of its :unitType.

### 3.4 Duration

The duration of an interval (or temporal sequence) can have many different descriptions. An interval can be 1 day 2 hours, or 26 hours, or 1560 minutes, and so on. It is useful to be able to talk about these descriptions in a convenient way as independent objects, and to talk about their equivalences. The extent of an interval can be given using multiple duration descriptions or individual durations (e.g., 2 days, 48 hours) , but these must all describe the same amount of time.
Four classes support the description of the duration of an entity. :TemporalDuration is the common super-class. :Duration has properties to describe the duration using a scaled number (i.e. a temporal quantity). :GeneralDurationDescription has a set of properties to specify a duration using calendar and clock elements, the definitions of which are given in the associated TRS description. Its subclass :DurationDescription fixes the temporal reference system to the Gregorian calendar, so the :hasTRS property may be omitted on individuals from this class.
:TemporalUnit is a standard duration which is used to scale a length of time, and to capture its granularity or precision.
Figure 4 Classes for temporal duration.
We use two different sets of properties for :GeneralDateTimeDescription or :DateTimeDescription, and :GeneralDurationDescription or :DurationDescription, because their ranges are different. For example, :year (in :DateTimeDescription) has a range of xsd:gYear which is a position in the Gregorian calendar, while :years (in :DurationDescription) has a range of xsd:decimal so that you can say "duration of 2.5 years".

## 4. Vocabulary specification

In this vocabulary specification, Manchester syntax [] is used where the value of a field is not a simple term denoted by a URI or cURI.

### 4.1 Classes

:DateTimeDescription | :DateTimeInterval | :DayOfWeek | :Duration | :DurationDescription | :GeneralDateTimeDescription | :GeneralDurationDescription | :Instant | :Interval | :MonthOfYear | :ProperInterval | :TemporalDuration | :TemporalEntity | :TemporalPosition | :TemporalUnit | :TimePosition | :TimeZone | :TRS

#### 4.1.1 Date-time description

Class:
Definition:
Description of date and time structured with separate values for the various elements of a calendar-clock system. The temporal reference system is fixed to Gregorian Calendar, and the range of year, month, day properties restricted to corresponding XML Schema types xsd:gYear, xsd:gMonth and xsd:gDay, respectively.
Subclass of:
Subclass of:
time:hasTRS value <
Subclass of:
time:year only xsd:gYear
Subclass of:
time:month only xsd:gMonth
Subclass of:
time:day only xsd:gDay
Other datetime concepts can be defined by specialization of :GeneralDateTimeDescription or :DateTimeDescription - see examples below.

#### 4.1.2 Date-time interval

Class:
Definition:
time:DateTimeInterval is a subclass of time:ProperInterval, defined using the multi-element time:DateTimeDescription.
Subclass of:
The class :DateTimeInterval is a subclass of :ProperInterval. It enables compact representation of an interval corresponding to a single element in a date-time description (i.e. a specified year, month, week, day, hour, minute, second). The property :hasDateTimeDescription describes the interval.
Note
:DateTimeInterval can only be used for an interval whose limits coincide with a date-time element aligned to the calendar and timezone indicated. For example, while both have a duration of one day, the 24-hour interval beginning at midnight at the beginning of 8 May in Central Europe can be expressed as a :DateTimeInterval, but the 24-hour interval starting at 1:30pm cannot.

#### 4.1.3 Day of week

Class:
Definition:
The day of week
Instance of:
Seven individual members of :DayOfWeek are included in the ontology, corresponding to the seven days used in the Gregorian calendar, and using the English names :Sunday, :Monday, :Tuesday, :Wednesday, :Thursday, :Friday, :Saturday.
Note
Membership of the class :DayOfWeek is open, to allow for alternative week lengths and different day names.

#### 4.1.4 Duration

Class:
Definition:
Duration of a temporal extent expressed as a decimal number scaled by a temporal unit
Subclass of:
:TemporalDuration
Subclass of:
time:numericDuration exactly 1
Subclass of:
time:unitType exactly 1

#### 4.1.5 Duration description

Class:
Definition:
Description of temporal extent structured with separate values for the various elements of a calendar-clock system. The temporal reference system is fixed to Gregorian Calendar, and the range of each of the numeric properties is restricted to xsd:decimal
Subclass of:
Subclass of:
time:hasTRS value <
Subclass of:
time:years only xsd:decimal
Subclass of:
time:months only xsd:decimal
Subclass of:
time:weeks only xsd:decimal
Subclass of:
time:days only xsd:decimal
Subclass of:
time:hours only xsd:decimal
Subclass of:
time:minutes only xsd:decimal
Subclass of:
time:seconds only xsd:decimal
Note
In the Gregorian calendar the length of the month is not fixed. Therefore, a value like "2.5 months" cannot be exactly compared with a similar duration expressed in terms of weeks or days.

#### 4.1.6 Generalized date-time description

Class:
Definition:
Description of date and time structured with separate values for the various elements of a calendar-clock system
Subclass of:
:TemporalPosition
Subclass of:
time:timeZone max 1
Subclass of:
time:unitType exactly 1
Subclass of:
time:year max 1
Subclass of:
time:month max 1
Subclass of:
time:day max 1
Subclass of:
time:hour max 1
Subclass of:
time:minute max 1
Subclass of:
time:second max 1
Subclass of:
time:week max 1
Subclass of:
time:dayOfYear max 1
Subclass of:
time:dayOfWeek max 1
Subclass of:
time:monthOfYear max 1
Two properties :timeZone, and :unitType, along with :hasTRS provide for reference information concerning the reference system and precision of temporal position values.
Six datatype properties :year, :month, :day, :hour, :minute, :second, together with :timeZone support the description of components of a temporal position in a calendar-clock system. These correspond with the 'seven property model' described in ISO 8601 [] and XML Schema Definition Language Part 2: Datatypes [], except that the calendar is not specified in advance, but is provided through the value of the :hasTRS property (defined above).
Some combinations of properties are redundant. For example, within a specified :year if :dayOfYear is provided then :day and :month can be computed, and vice versa. Individual values SHOULD be consistent with each other and the calendar, indicated through the value of the :hasTRS property.
Two additional properties :week and :dayOfYear allow for the numeric value of the week or day relative to the year. The property :dayOfWeek provides the name of the day, and the property :monthOfYear provides the name of the month.

#### 4.1.7 Generalized duration description

Class:
Definition:
Description of temporal extent structured with separate values for the various elements of a calendar-clock system.
Subclass of:
:TemporalDuration
Subclass of:
time:hasTRS exactly 1
Subclass of:
time:years max 1
Subclass of:
time:months max 1
Subclass of:
time:weeks max 1
Subclass of:
time:days max 1
Subclass of:
time:hours max 1
Subclass of:
time:minutes max 1
Subclass of:
time:seconds max 1
Seven datatype properties :years, :months, :weeks, :days, :hours, :minutes, and :seconds support the description of components of a temporal extent in a calendar-clock system.
The property time:hasTRS indicates the temporal reference system applicable for the duration components.
Note
The extent of a time duration expressed as a GeneralDurationDescription depends on the Temporal Reference System. In some calendars the length of the week or month is not constant within the year. Therefore, a value like "2.5 months" may not necessarily be exactly compared with a similar duration expressed in terms of weeks or days. When non-earth-based calendars are considered even more care must be taken in comparing durations.

#### 4.1.8 Time instant

Class:
Definition:
A temporal entity with zero extent or duration
Subclass of:
Seven properties, :inXSDDate, :inXSDDateTime (deprecated), :inXSDDateTimeStamp, :inXSDgYear, :inXSDgYearMonth, :inTimePosition, and :inDateTime provide alternative ways to describe the temporal position of an :Instant.

#### 4.1.9 Time interval

Class:
Definition:
A temporal entity with an extent or duration
Subclass of:
One property :inside links to an :Instant that falls inside the :Interval.

#### 4.1.10 Month of year

Class:
Definition:
The month of the year
Subclass of:
Subclass of:
time:year exactly 0
Subclass of:
time:month exactly 1
Subclass of:
time:week exactly 0
Subclass of:
time:day exactly 0
Subclass of:
time:hour exactly 0
Subclass of:
time:minute exactly 0
Subclass of:
time:second exactly 0
Subclass of:
time:unitType value time:unitMonth
Twelve individual members of :MonthOfYear are provided in a separate namespace, corresponding to the twelve months used in the Gregorian calendar greg:January, greg:February, greg:March, greg:April, greg:May, greg:June, greg:July, greg:August, greg:September, greg:October, greg:November, greg:December. Each month is defined by setting the value of time:month to the corresponding value.
Note
Membership of the class :MonthOfYear is open, to allow for alternative annual calendars and different month names.

#### 4.1.11 Proper interval

Class:
Definition:
A temporal entity with non-zero extent or duration, i.e. for which the value of the beginning and end are different
Subclass of:
Disjoint with:
Fifteen properties :intervalBefore, :intervalAfter, :intervalMeets, :intervalMetBy, :intervalOverlaps, :intervalOverlappedBy, :intervalStarts, :intervalStartedBy, :intervalDuring, :intervalContains, :intervalFinishes, :intervalFinishedBy, :intervalEquals :intervalDisjoint :intervalIn support the set of interval relations defined by Allen [] and Allen and Ferguson [].

#### 4.1.12 Temporal duration

Class:
Definition:
Time extent; duration of a time interval separate from its particular start position
Instance of:

#### 4.1.13 Temporal entity

Class:
Definition:
A temporal interval or instant.
Instance of:
Union of:
Two properties, :before, :after, support ordering relationships between two :TemporalEntitys.
The properties :hasBeginning, :hasEnd and :hasTemporalDuration (or its sub-properties), support the description of the bounds and extent of a :TemporalEntity.

#### 4.1.14 Temporal position

Class:
Definition:
A position on a time-line
Instance of:
Subclass of:
time:hasTRS exactly 1
The property time:hasTRS indicates the temporal reference system.

#### 4.1.15 Temporal unit

Class:
Definition:
A standard duration, which provides the scale factor for a time extent, or the granularity or precision for a time position.
Subclass of:
Seven individual members of :TemporalUnit are included in the ontology, corresponding to the elements of the standard calendar-clock: :unitYear, :unitMonth, :unitWeek, :unitDay, :unitHour, :unitMinute and :unitSecond.
Note
Membership of the class TemporalUnit is open, to allow for other temporal units used in some technical applications (e.g. millions of years, Baha'i month).

#### 4.1.16 Time position

Class:
Definition:
A temporal position described using either a (nominal) value from an ordinal reference system, or a (numeric) value in a temporal coordinate system.
Subclass of:
:TemporalPosition
Subclass of:
( time:numericPosition exactly 1 ) or ( time:nominalPosition exactly 1 )
Two properties :nominalPosition and :numericPosition support the alternative descriptions of position or extent. One of these is expected to be present.
The temporal ordinal reference system should be provided as the value of the :hasTRS property
The temporal coordinate system should be provided as the value of the :hasTRS property

#### 4.1.17 Time-zone

Class:
Definition:
A Time Zone specifies the amount by which the local time is offset from UTC. A time zone is usually denoted geographically (e.g. Australian Eastern Daylight Time), with a constant value in a given region. The region where it applies and the offset from UTC are specified by a locally recognised governing authority.
Instance of:
No specific properties are provided for the class :TimeZone, the definition of which is beyond the scope of this ontology. The class specified here is a stub, effectively the superclass of all time zone classes.
Note
An ontology for time zone descriptions was described in [] and provided as RDF in a separate namespace tzont:. However, that ontology was incomplete in scope, and the example datasets were selective. Furthermore, since the use of a class from an external ontology as the range of an ObjectProperty in OWL-Time creates a dependency, reference to the time zone class has been replaced with the 'stub' class in the normative part of this version of OWL-Time.
Note
A designated timezone is associated with a geographic region. However, for a particular region the offset from UTC often varies seasonally, and the dates of the changes may vary from year to year. The timezone designation usually changes for the different seasons (e.g. Australian Eastern Standard Time vs. Australian Eastern Daylight Time). Furthermore, the offset for a timezone may change over longer timescales, though its designation might not.
Detailed guidance about working with time zones is given in [].

#### 4.1.18 Temporal reference system

Class:
Definition:
A temporal reference system, such as a temporal coordinate system (with an origin, direction, and scale), a calendar-clock combination, or a (possibly hierarchical) ordinal system.
Instance of:
No specific properties are provided for the class :TRS, the definition of which is beyond the scope of this ontology. The class specified here is a stub, effectively the superclass of all temporal reference system types.
Note that an ordinal temporal reference system, such as the geologic timescale, may be represented directly, using this ontology, as a set of :ProperIntervals, along with enough inter-relationships to support the necessary ordering relationships. See example below of Geologic Timescale.
Note
A taxonomy of temporal reference systems is provided in ISO 19108:2002 [], including (a) calendar + clock systems; (b) temporal coordinate systems (i.e. numeric offset from an epoch); (c) temporal ordinal reference systems (i.e. ordered sequence of named intervals, not necessarily of equal duration).

### 4.2 Properties

:after | :before | :day | :dayOfWeek | :dayOfYear | :days | :hasBeginning | :hasDateTimeDescription | :hasDuration | :hasDurationDescription | :hasEnd | :hasTemporalDuration | :hasTime | :hasTRS | :hasXSDDuration | :hour | :hours | :inDateTime | :inside | :inTemporalPosition | :intervalAfter | :intervalBefore | :intervalContains | :intervalDisjoint | :intervalDuring | :intervalEquals | :intervalFinishedBy | :intervalFinishes | :intervalIn | :intervalMeets | :intervalMetBy | :intervalOverlappedBy | :intervalOverlaps | :intervalStartedBy | :intervalStarts | :inTimePosition | :inXSDDate | :inXSDDateTime | :inXSDDateTimeStamp | :inXSDgYear | :inXSDgYearMonth | :minute | :minutes | :month | :monthOfYear | :months | :nominalPosition | :numericDuration | :numericPosition | :second | :seconds | :timeZone | :unitType | :week | :weeks | :xsdDateTime | :year | :years

#### 4.2.1 after

Property:
Definition:
Gives directionality to time. If a temporal entity T1 is after another temporal entity T2, then the beginning of T1 is after the end of T2.
Instance of:
Domain:
Range:
Inverse Property:

#### 4.2.2 before

Property:
Definition:
Gives directionality to time. If a temporal entity T1 is before another temporal entity T2, then the end of T1 is before the beginning of T2. Thus, before can be considered to be basic to instants and derived for intervals.
Instance of:
Domain:
Range:
Inverse Property:

#### 4.2.3 day

Property:
Definition:
Day position in a calendar-clock system. The range of this property is not specified, so can be replaced by any specific representation of a calendar day from any calendar.
Instance of:
Domain:

#### 4.2.4 day of week

Property:
Definition:
The day of week, whose value is a member of the class time:DayOfWeek
Instance of:
Domain:
Range:

#### 4.2.5 day of year

Property:
Definition:
The number of the day within the year
Instance of:
Domain:
Range:

#### 4.2.6 days duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in days
Instance of:
Domain:
Range:

#### 4.2.7 has beginning

Property:
Definition:
Beginning of a temporal entity.
Instance of:
Domain:
Range:

#### 4.2.8 has date-time description

Property:
Definition:
Position and extent of time:DateTimeInterval expressed as a structured value. The beginning and end of the interval coincide with the limits of the shortest element in the description.
Instance of:
Domain:
Range:

#### 4.2.9 has duration

Property:
Definition:
Duration of a temporal entity, expressed as a scaled value or nominal value
Instance of:
Subproperty of:
Range:

#### 4.2.10 has duration description

Property:
Definition:
Duration of a temporal entity, expressed using a structured description
Instance of:
Subproperty of:
Range:

#### 4.2.11 has end

Property:
Definition:
End of a temporal entity.
Instance of:
Domain:
Range:

#### 4.2.12 has temporal duration

Property:
Definition:
Duration of a temporal entity
Instance of:
Domain:
Range:

#### 4.2.13 has time

Property:
Definition:
Supports the association of a temporal entity (instant or interval) to any thing.
Instance of:
Range:

#### 4.2.14 temporal reference system used

Property:
Definition:
The temporal reference system used by a temporal position or extent description.
Instance of:
Instance of:
Domain:
time:TemporalPosition or time:GeneralDurationDescription
Range:

#### 4.2.15 has XSD duration

Property:
Definition:
Extent of a temporal entity, expressed using xsd:duration
Instance of:
Domain:
Range:

#### 4.2.16 hour

Property:
Definition:
Hour position in a calendar-clock system
Instance of:
Domain:
Range:

#### 4.2.17 hours duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in hours
Instance of:
Domain:
Range:

#### 4.2.18 in date-time description

Property:
Definition:
Position of an instant, expressed using a structured description
Instance of:
Subproperty of:
Domain:
Range:

#### 4.2.19 has time instant inside

Property:
Definition:
An instant that falls inside the interval. It is not intended to include beginnings and ends of intervals.
Instance of:
Domain:
Range:

#### 4.2.20 temporal position

Property:
Definition:
Position of a time instant
Instance of:
Domain:
Range:

#### 4.2.21 interval after

Property:
Definition:
If a proper interval T1 is intervalAfter another proper interval T2, then the beginning of T1 is after the end of T2.
Instance of:
Domain:
Range:
SubProperty of:
SubProperty of:
Inverse of:

#### 4.2.22 interval before

Property:
Definition:
If a proper interval T1 is intervalBefore another proper interval T2, then the end of T1 is before the beginning of T2.
Instance of:
Domain:
Range:
SubProperty of:
SubProperty of:
Inverse of:

#### 4.2.23 interval contains

Property:
Definition:
If a proper interval T1 is intervalContains another proper interval T2, then the beginning of T1 is before the beginning of T2, and the end of T1 is after the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.24 interval disjoint

Property:
Definition:
If a proper interval T1 is intervalDisjoint another proper interval T2, then the beginning of T1 is after the end of T2, or the end of T1 is before the beginning of T2, i.e. the intervals do not overlap in any way, but their ordering relationship is not known.
Instance of:
Domain:
Range:

#### 4.2.25 interval during

Property:
Definition:
If a proper interval T1 is intervalDuring another proper interval T2, then the beginning of T1 is after the beginning of T2, and the end of T1 is before the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.26 interval equals

Property:
Definition:
If a proper interval T1 is intervalEquals another proper interval T2, then the beginning of T1 is coincident with the beginning of T2, and the end of T1 is coincident with the end of T2.
Instance of:
Domain:
Range:
Disjoint with:

#### 4.2.27 interval finished by

Property:
Definition:
If a proper interval T1 is intervalFinishedBy another proper interval T2, then the beginning of T1 is before the beginning of T2, and the end of T1 is coincident with the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.28 interval finishes

Property:
Definition:
If a proper interval T1 is intervalFinishes another proper interval T2, then the beginning of T1 is after the beginning of T2, and the end of T1 is coincident with the end of T2.
Instance of:
Domain:
Range:
SubProperty of:
Inverse of:

#### 4.2.29 interval in

Property:
Definition:
If a proper interval T1 is intervalIn another proper interval T2, then the beginning of T1 is after the beginning of T2 or is coincident with the beginning of T2, and the end of T1 is before the end of T2 or is coincident with the end of T2, except that end of T1 may not be coincident with the end of T2 if the beginning of T1 is coincident with the beginning of T2.
Instance of:
Domain:
Range:
Disjoint with:

#### 4.2.30 interval meets

Property:
Definition:
If a proper interval T1 is intervalMeets another proper interval T2, then the end of T1 is coincident with the beginning of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.31 interval met by

Property:
Definition:
If a proper interval T1 is intervalMetBy another proper interval T2, then the beginning of T1 is coincident with the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.32 interval overlapped by

Property:
Definition:
If a proper interval T1 is intervalOverlappedBy another proper interval T2, then the beginning of T1 is after the beginning of T2, the beginning of T1 is before the end of T2, and the end of T1 is after the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.33 interval overlaps

Property:
Definition:
If a proper interval T1 is intervalOverlaps another proper interval T2, then the beginning of T1 is before the beginning of T2, the end of T1 is after the beginning of T2, and the end of T1 is before the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.34 interval started by

Property:
Definition:
If a proper interval T1 is intervalStartedBy another proper interval T2, then the beginning of T1 is coincident with the beginning of T2, and the end of T1 is after the end of T2.
Instance of:
Domain:
Range:
Inverse of:

#### 4.2.35 interval starts

Property:
Definition:
If a proper interval T1 is intervalStarts another proper interval T2, then the beginning of T1 is coincident with the beginning of T2, and the end of T1 is before the end of T2.
Instance of:
Domain:
Range:
SubProperty of:
Inverse of:

#### 4.2.36 time position

Property:
Definition:
Position of an instant, expressed as a temporal coordinate or nominal value
Instance of:
Domain:
Range:
Subproperty of:

#### 4.2.37 in XSD date

Property:
Definition:
Position of an instant, expressed using xsd:date
Instance of:
Domain:
Range:

#### 4.2.38 in XSD date-time

Property:
Definition:
Position of an instant, expressed using xsd:dateTime
Instance of:
Instance of:
Domain:
Range:
Deprecated:
true
Note
The property :inXSDDateTime is replaced by :inXSDDateTimeStamp which makes the time-zone field mandatory.

#### 4.2.39 in XSD date-time-stamp

Property:
Definition:
Position of an instant, expressed using xsd:dateTimeStamp, in which the time-zone field is mandatory
Instance of:
Domain:
Range:

#### 4.2.40 in XSD gYear

Property:
Definition:
Position of an instant, expressed using xsd:gYear
Instance of:
Domain:
Range:

#### 4.2.41 in XSD gYearMonth

Property:
Definition:
Position of an instant, expressed using xsd:gYearMonth
Instance of:
Domain:
Range:

#### 4.2.42 minute

Property:
Definition:
Minute position in a calendar-clock system
Instance of:
Domain:
Range:

#### 4.2.43 minutes duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in minutes
Instance of:
Domain:
Range:

#### 4.2.44 month

Property:
Definition:
Month position in a calendar-clock system. The range of this property is not specified, so can be replaced by any specific representation of a calendar month from any calendar.
Instance of:
Domain:

#### 4.2.45 month of year

Property:
Definition:
The month of the year, whose value is a member of the class time:MonthOfYear
Instance of:
Domain:
Range:

#### 4.2.46 months duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in months
Instance of:
Domain:
Range:

#### 4.2.47 name of temporal position

Property:
Definition:
The (nominal) value indicating temporal position in an ordinal reference system
Instance of:
Domain:
Range:

#### 4.2.48 numeric value of temporal duration

Property:
Definition:
Value of a temporal extent expressed as a number scaled by a temporal unit
Instance of:
Domain:
Range:

#### 4.2.49 numeric value of temporal position

Property:
Definition:
The (numeric) value indicating position within a temporal coordinate system
Instance of:
Domain:
Range:

#### 4.2.50 second

Property:
Definition:
Second position in a calendar-clock system.
Instance of:
Domain:
Range:

#### 4.2.51 seconds duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in seconds
Instance of:
Domain:
Range:

#### 4.2.52 in time zone

Property:
Definition:
The time zone for clock elements in the temporal position
Instance of:
Domain:
Range:
Note
IANA maintains a database of timezones. These are well maintained and generally considered authoritative, but individual items are not available at individual URIs, so cannot be used directly within data expressed using OWL-Time.
DBPedia provides a set of resources corresponding to the IANA timezones, with a URI for each (e.g. The World Clock service also provides a list of time zones with the description of each available as an individual webpage with a convenient individual URI (e.g. These or other, similar, resources might be used as a value of the time:timeZone property.

#### 4.2.53 temporal unit type

Property:
Definition:
The temporal unit which provides the precision of a date-time value or scale of a temporal extent
Instance of:
Domain:
time:GeneralDateTimeDescription or time:Duration
Range:

#### 4.2.54 week

Property:
Definition:
Week number within the year.
Instance of:
Domain:
Range:
Note
Weeks are numbered differently depending on the calendar in use and the local language or cultural conventions (locale). ISO-8601 specifies that the first week of the year includes at least four days, and that Monday is the first day of the week. In that system, week 1 is the week that contains the first Thursday in the year.

#### 4.2.55 weeks duration

Property:
:weeks
Definition:
length of, or element of the length of, a temporal extent expressed in weeks
Instance of:
Domain:
Range:

#### 4.2.56 has XSD date-time

Property:
Definition:
Value of time:DateTimeInterval expressed as a compact value. The beginning and end of the interval coincide with the limits of the smallest non-zero element of the value.
Instance of:
Instance of:
Domain:
Range:
Deprecated:
true
Note
Using xsd:dateTime in this place means that the duration of the interval is implicit: it corresponds to the length of the smallest non-zero element of the date-time literal. However, this rule cannot be used for intervals whose duration is more than one rank smaller than the starting time - e.g. the first minute or second of a day, the first hour of a month, or the first day of a year. In these cases the desired interval cannot be distinguished from the interval corresponding to the next rank up. Because of this essential ambiguity, use of this property is not recommended and it is deprecated.

#### 4.2.57 year

Property:
Definition:
Year position in a calendar-clock system. The range of this property is not specified, so can be replaced by any specific representation of a calendar year from any calendar.
Instance of:
Domain:

#### 4.2.58 years duration

Property:
Definition:
length of, or element of the length of, a temporal extent expressed in years
Instance of:
Domain:
Range:

### 4.3 Datatypes

:generalDay | :generalMonth | :generalYear

#### 4.3.1 generalDay

Class:
Definition:
Day of month - formulated as a text string with a pattern constraint to reproduce the same lexical form as xsd:gDay, except that values up to 99 are permitted, in order to support calendars with more than 31 days in a month. Note that the value-space is not defined, so a generic OWL2 processor cannot compute ordering relationships of values of this type.
Instance of:
Subclass of:

#### 4.3.2 generalMonth

Class:
Definition:
Month of year - formulated as a text string with a pattern constraint to reproduce the same lexical form as xsd:gMonth, except that values up to 20 are permitted, in order to support calendars with more than 12 months in the year. Note that the value-space is not defined, so a generic OWL2 processor cannot compute ordering relationships of values of this type.
Instance of:
Subclass of:

#### 4.3.3 generalYear

Class:
Definition:
Year number - formulated as a text string with a pattern constraint to reproduce the same lexical form as xsd:gYear, but not restricted to values from the Gregorian calendar. Note that the value-space is not defined, so a generic OWL2 processor cannot compute ordering relationships of values of this type.
Instance of:
Subclass of:

### 4.4 Individuals

:Friday | :Monday | :Saturday | :Sunday | :Thursday | :Tuesday | :Wednesday | :unitDay | :unitHour | :unitMinute | :unitMonth | :unitSecond | :unitWeek | :unitYear | greg:April | greg:August | greg:December | greg:February | greg:January | greg:July | greg:June | greg:March | greg:May | greg:November | greg:October | greg:September
Class
Individual

## 5. Examples

This section is non-normative.

### 5.1 DateTimeDescription vs dateTime

The following example illustrates the difference between using :DateTimeDescription and using the XML datatype xsd:dateTimeStamp. An instant that represents the start of a meeting, called ex:meetingStart, happens at 10:30am AEST on 12 Apr 2017 can be expressed using both :inXSDDateTimeStamp and :inDateTime in OWL as:
It is much more concise to use the XML Schema datatype xsd:dateTimeStamp. However, using :DateTimeDescription more information can be included directly in a message, such as the "week", "day of week" and "day of year". In the example we can also see that 12/04/2017 is a Wednesday, the month is April, it is the 102nd day of the year, and in the 15th week of the year. Since each field of :DateTimeDescription is separate no computation is required to get the values of these fields for use in reasoning. However, since some calendars, such as religious observationally-based ones, cannot be algorithmically calculated explicit assertion of values for elements of the calendar is required.
The :timeZone property points to a definition of Australian Eastern Standard Time.

### 5.2 Use of temporal reference systems

The use of different temporal reference systems for the same absolute time is illustrated in the following examples. Abby's birthday is an :Instant whose position may be expressed using the conventional XSD xsd:dateTimeStamp type as 2001-05-23T08:20:00+08:00:
Using the :DateTimeDescription class, the elements of the date and time using the Gregorian Calendar are split out into separate properties:
The :GeneralDateTimeDescription class may be used to express the same date using the Hebrew calendar:
The :TimePosition class may be used to express the same position in Unix time (also known as Posix time or Epoch time) (i.e. the number of seconds since the beginning of 1st January 1970):
Each of these examples refers to either a temporal reference system or time zone described externally, using its URI. RDF representations are available from DBPedia (e.g. though these do not have specific time semantics.
Similar to the way that :DateTimeDescription is a derived from :GeneralDateTimeDescription by fixing the :TRS to the Gregorian system, a specialized class UnixTime may be derived from :TimePosition by fixing the value of its reference system to the Unix time system:
The RDF representation of this example is available here.

### 5.3 Temporal precision

For the purposes of radiocarbon dating (which is the technique used in geological age determination for materials up to around 60,000 years old) 'the Present' is conventionally fixed at 1950 []. This can be described as an individual :Instant, with its position expressed using any of the three alternatives:
Expressed using :DateTimeDescription the :unitType - which determines the precision - is set to :unitYear, and only the :year element is provided in the value. The TRS value is not provided explicitly, as it is fixed in the ontology description to In the :TimePosition variant, the TRS is given as which has units of millions of years, starting from the present, positive backwards. For the value expressed using xsd:dateTimeStamp the position within the year is set arbitrarily to midnight at the beginning of 1st January. This level of precision in this case is spurious, but is required to satisfy the lexical pattern of the datatype.
Since the :numericPosition, :second properties have the datatype of xsd:decimal, the position of a :Instant or the duration of a :TemporalEntity may be represented with a precision of fractions of seconds if required. For example, a database timestamp with a precision of milliseconds can be expressed as follows:
where ex:GPSTime specializes :GeneralDateTimeDescription by setting the :unitType to :unitSecond, the :hasTRS to the GPS timekeeping system, and suppressing all other properties except for :week and :second:

### 5.4 iCalendar

iCalendar [] is a widely supported standard for personal data interchange. It provides the definition of a common format for openly exchanging calendaring and scheduling information across the Internet. The representation of temporal concepts in this time ontology can be straightforwardly mapped to iCalendar. For example, duration of 15 days, 5 hours and 20 seconds is represented in iCalendar as P15DT5H0M20S, which can be represented in the time ontology as:
The iCalendar homepage features the example of Abraham Lincoln's birthday as celebrated in 2008. This may be represented in multiple ways using OWL-Time, including the following.
As a :DateTimeInterval using the :DateTimeDescription form:
The boundaries of the interval are implicitly the beginning and end of the day specified in the :DateTimeDescription.
As a :TemporalEntity using the :TimePosition to define the beginning and end:
In this formulation, the length of the entity is explicit, as the value of the :hasDuration property.
Several other formulations are possible, some of which are shown in the RDF representation is available here.

### 5.5 Geologic timescale

The geologic timescale is defined as a set of named intervals arranged in a hierarchy, such that there is only one subdivision of the intervals of each rank (e.g. 'Era') by a set of intervals of the next rank (in this case 'Period') []. Since the relative ordering is well-defined this graph can therefore serve as an ordinal temporal reference system. Fig. 5 shows how the geologic timescale can be expressed as a set of :ProperIntervals related to each other using only :intervalMetBy, :intervalStartedBy, :intervalFinishedBy. Many other interval relationships follow logically from the ones shown (for example 'Neogene Period' :intervalDuring 'Cenozoic Era') but the ones shown are sufficient to describe the full topology.
Figure 5 Part of the geologic timescale formalized as ProperIntervals, with ordering relationships described using the predicates defined in this ontology.
For example, the 'Archean Eon' is a :ProperInterval described as follows:
The beginning of the Archean Eon is an :Instant, described as follows:
Note that the position of this :Instant is specified using a :TimePosition, which is a numeric value relative to the temporal coordinate system indicated as the value of the :hasTRS property.
The RDF representation of this example is available here. The complete (2016) International Chronostratigraphic Chart encoded using OWL-Time is available.

### 5.6 A Use Case for Scheduling

Suppose someone has a telecon scheduled for 6:00pm EST on November 5, 2006. You would like to make an appointment with him for 2:00pm PST on the same day, and expect the meeting to last 45 minutes. Will there be an overlap?
In this use case we can specify the facts about the telecon and the meeting using our ontology in OWL that will allow a temporal reasoner to determine whether there is a conflict:
The telecon and the meeting are defined as intervals. :hasBeginning is used for specifying the start times of the meetings. The datetimes are specified using :inXSDDateTimeStamp. The duration of the meeting is specified using the :DurationDescription class.

### 5.7 Alignment of PROV-O with OWL-Time

PROV is a process-flow model. The base class Activity denotes things that occur over a period of time, and act upon or with entities. Activities are ordered within a provenance trace. Thus, an alignment with OWL-Time is natural.
The PROV-O classes prov:Activity and prov:InstantaneousEvent may be conceived as sub-classes of :TemporalEntity and :Instant respectively.
The prov:atTime property of an prov:InstantaneousEvent is directly related to :inXSDDateTime.
However, the Activity start and end properties require a property chain axiom, because the beginning and end of a :TemporalEntity are :Instants rather than compact xsd:dateTimes.

### 5.8 Legal interval

The basic example in the [] specification described the 'temporal range' of a dataset with reference to the resource which is one of many available from data.gov.uk. This resource defines a specific legal period - the first quarter of 2006 - formalized using the interval ontology which is (currently) based on the 2006 version of OWL-Time. The period can be fully described using OWL-Time, omitting all elements from the intervals ontology, as follows:

## A. Summary of Classes and Properties in the Time Ontology

Items in italics were added in the 2017 revision of OWL-Time and are not yet widely used. These may be considered features at risk.

### A.1 Classes (subclass relations)

- :TemporalEntity
- :Instant
- :Interval
- :ProperInterval
- :DateTimeInterval
- :TemporalPosition
- :TimePosition
- :GeneralDateTimeDescription
- :DateTimeDescription
- :MonthOfYear
- :TemporalDuration
- :Duration
- :GeneralDurationDescription
- :DurationDescription
- :TemporalUnit
- :TRS
- :TimeZone
- :DayOfWeek

### A.2 Properties (sorted by domain value)

Property Name
Domain
Range
:hasTime
:TemporalEntity
:hasBeginning
:TemporalEntity
:Instant
:hasEnd
:TemporalEntity
:Instant
:hasTemporalDuration
:TemporalEntity
:TemporalDuration
:hasDuration
:TemporalEntity
:Duration
:hasDurationDescription
:TemporalEntity
:GeneralDurationDescription
:hasXSDDuration
:TemporalEntity
:before
:TemporalEntity
:TemporalEntity
:after
:TemporalEntity
:TemporalEntity
:inside
:Interval
:Instant
:intervalEquals
:ProperInterval
:ProperInterval
:intervalDisjoint
:ProperInterval
:ProperInterval
:intervalAfter
:ProperInterval
:ProperInterval
:intervalBefore
:ProperInterval
:ProperInterval
:intervalMeets
:ProperInterval
:ProperInterval
:intervalMetBy
:ProperInterval
:ProperInterval
:intervalOverlaps
:ProperInterval
:ProperInterval
:intervalOverlappedBy
:ProperInterval
:ProperInterval
:intervalStarts
:ProperInterval
:ProperInterval
:intervalStartedBy
:ProperInterval
:ProperInterval
:intervalFinishes
:ProperInterval
:ProperInterval
:intervalFinishedBy
:ProperInterval
:ProperInterval
:intervalContains
:ProperInterval
:ProperInterval
:intervalDuring
:ProperInterval
:ProperInterval
:intervalIn
:ProperInterval
:ProperInterval
:hasDateTimeDescription
:DateTimeInterval
:GeneralDateTimeDescription
:xsdDateTime (deprecated)
:DateTimeInterval
:inTemporalPosition
:Instant
:TemporalPosition
:inTimePosition
:Instant
:TimePosition
:inDateTime
:Instant
:GeneralDateTimeDescription
:inXSDDate
:Instant
:inXSDDateTime (deprecated)
:Instant
:inXSDDateTimeStamp
:Instant
:inXSDgYearMonth
:Instant
:inXSDgYear
:Instant
:numericDuration
:Duration
:unitType
:Duration or :GeneralDateTimeDescription
:TemporalUnit
:years
:GeneralDurationDescription
:months
:GeneralDurationDescription
:weeks
:GeneralDurationDescription
:days
:GeneralDurationDescription
:hours
:GeneralDurationDescription
:minutes
:GeneralDurationDescription
:seconds
:GeneralDurationDescription
:numericPosition
:TimePosition
:nominalPosition
:TimePosition
:timeZone
:GeneralDateTimeDescription
:TimeZone
:year
:GeneralDateTimeDescription
:month
:GeneralDateTimeDescription
:day
:GeneralDateTimeDescription
:hour
:GeneralDateTimeDescription
:minute
:GeneralDateTimeDescription
:second
:GeneralDateTimeDescription
:week
:GeneralDateTimeDescription
:dayOfYear
:GeneralDateTimeDescription
:dayOfWeek
:GeneralDateTimeDescription
:DayOfWeek
:monthOfYear
:GeneralDateTimeDescription
:MonthOfYear
:hasTRS
:TemporalPosition or :GeneralDurationDescription
:TRS

### A.3 Datatypes

- :generalDay
- :generalMonth
- :generalYear

## B. Implementation report

OWL-Time has been put into use in a large number of applications. Some of these are summarized here.

## D. Wide review

Results of wide review of OWL-Time is summarized here.

## E. Response to Requirements identified in working group analysis

A number of requirements relating to Time were identified in the Spatial Data on the Web Use Cases & Requirements []. This section provides brief descriptions of how these requirements have been resolved.
- 5.7 Date, time and duration: see overview, time:TemporalEntity, time:TemporalPosition, time:TemporalDuration
- 5.53 Update datatypes in OWL Time: see time:inXSDDateTimeStamp and Datatypes
- 5.9 Different time models: see trs-clock-calendar, time:TRS, time:hasTRS
- 5.48 Temporal reference system: see trs-clock-calendar, time:TRS, time:hasTRS
- 5.28 Nominal temporal references: see time:TimePosition, time:nominalPosition
- 5.56 Valid time: not resolved explicitly. A specialization of time:hasTime can be used
- 5.49 Temporal vagueness: not addressed explicitly, but interval relations single-ended intervals may be used for some cases
- 5.51 Time series: out of scope for OWL-Time which is concerned with the representation of the temporal aspects only. Coverages in Linked Data provides some support
- 5.39 Space-time multi-scale: OWL-Time supports the representation of the temporal properties of things, so may be used as a component of an integrated solution, but the latter is out of scope for this document.
- 5.22 4D model of space-time: OWL-Time supports the representation of time that may be used in 4D applications. In particular the classes time:Duration and time:TimePosition support descriptions of time duration as a scaled number, and time position as a time coordinate.
- 5.32 Provenance: individuals from classes in the time:TemporalEntity hierarchy may be used in the description of activities involved in provenance traces. prov:Activity could itself be modelled as an rdfs:subClassOf of time:TemporalEntity. Allen's interval algebra described in topology can support the description of temporal relationships between activities in a provenance trace. However, these applications have not been explicitly modelled in this document.
- 5.25 Multilingual support: all labels and other annotations in the ontology have correct language tags. Individuals from the classes time:DayOfWeek and time:MonthOfYear have labels in several languages in the RDF artefacts.

## F. Acknowledgements

The editors would like to thank the members of the W3C/OGC Spatial Data on the Web Working Group for their contributions during the development of this document.
