# Core

## Flows of value

Value means useful economic resources. Flows means how people create, combine, move, and exchange them.

Networks of value flows are created when processes and transfers are linked together through flows of resources.

Flow-oriented systems can coordinate whole networks as easily as one company.

## The patterns used in Valueflows

There are two basic patterns used in Valueflows:

* Resources, Events, and Agents (REA)

* Input-Process-Output Resource Flows (IPO)

## REA (Resources, Events, Agents)

The core is based on the REA (Resource, Event, Agent) ontology.  You can find all the details by following the links here.

**Agents** are individual persons or organizations or ecological agents, who perform Economic Events affecting Economic Resources.

An **Economic Event** can take actions like produce, modify, consume, or use Economic Resources, or transfer them from one Agent to another, or transport them from one location to another.

**Economic Resources** would typically be useful goods and services, but could also be money, credits, energy, knowledge, designs, skills, CO2, methane, air, water, or almost anything else that some Agents can agree should be accounted for in their economic networks.

## IPO (Input-Process-Output)

The IPO pattern is used to enhance the ability of REA to represent complex flows of value.  The flows are IPOs...

...Input-Process-Output resource chains, where one **Economic Resource** is the output of one **Process** and then becomes an input to another, thus connecting the processes into a flow. The **Agents** involved in each Process in the chain need to coordinate with the previous and next Processes about the quantity, quality, and timing of resource flows between them.

## Putting them together

In general, how they fit together: Agents perform Economic Events that provide Inputs to Processes and take Outputs from Processes and move Resources from one Process to another.  This forms a directed graph of value flows.

For example: a food network

...might include farmers, food processors, restaurants and bakeries, grocery stores, families to eat the food. And vehicles to move everything from place to place. Coordination might be needed between each of those stages: seeds and other inputs for planting crops, workers etc for harvesting crops. when are the crops ready for processing, when is the grain ready for milling and then for baking and then for people to eat, when is the fruit ready for pies, etc.

## Flows without processes

Some flows do not involve processing, i.e. there is no transformation or transportation of Economic Resources.  These flows simply transfer Economic Resources between Agents. One common example is an exchange of one Economic Resource for another Economic Resource between two Agents, as below, with two reciprocal flows based on an Agreement.

It can also be simpler, such as a gift, or more complex, involving many Agents.  Also, these flows can mix in with Process-based flows.

For example: in that food network above

...food processors might purchase the harvested food from farmers, sell processed food to restaurants and stores... or families might provide land and labor for a farm and receive harvested food each week in return.  That becomes part of the coordination.

## Types of flows

These are the main types of flows and how they relate as stages of value flows.  They have basically the same core data structure, with differences related to their stage.  Any of these types can be input or output to a process, or reciprocally related, as above.

## Traversing value flows

Value flows can be traversed forwards ("tracking") or backwards ("tracing").  Often people use the term "provenance" when looking backwards towards the source of some resource, sometimes when a problem emerges (as in a disease outbreak from food), sometimes to know the quality of the resource (as in wanting local humanely produced food with lower ecological impact).

The data structures of Valueflows provide the ability to trace or track any value flow, no matter how long or complex, see Track and Trace.

## Levels of the ontology

Valueflows uses the layers of ontology documented by REA.  Each of the layers follows the core patterns above.

* The Knowledge level represents classification, policies, procedures, rules and patterns. This is where each network or community can configure the core concepts to fit their needs.
* The Plan level represents offers and requests, schedules and promises.
* The Observation level represents what really happened.

Here is a simplified view of how they connect.

Here is a specific simplified example:

# Diagram Explanations

These textual explanations are a break-down of the UML diagram on the previous page.  The explanations are organized by class within subject area of the model.

### Agent

The Agent subject area defines roles in the Knowledge Layer and defines agents and their relationships in the Observation Layer.  More info at Agent concepts and Ecological Agents.

#### vf:Agent

The Valueflows view of Agent is fairly broad, including people, organizations (formal or informal), and ecological agents such as non-human beings and ecosystems.  But all of these have economic or governance agency of some sort.

Agents are key to the overall ontology, particularly the flows in Planning and Observation: Intents, Commitments, EconomicEvents, Claims, where each can reference a provider and receiver Agent. Proposals can be published to Agent(s), and Agents can have many AgentRelationships with other Agents of any type.

There are 3 subclasses of Agent: **vf:Person**, **vf:Organization**, and **vf:EcologicalAgent**.

#### vf:AgentRelationship

The subject and object of an AgentRelationship are Agents.  Their role the subject plays in relation to the object is represented by the AgentRelationshipRole.  Agents can have multiple relationships and multiple kinds of relationships in the same network.

#### vf:AgentRelationshipRole

Agent relationship roles define the roles or types of agent relationships within a network, completely defined by the network itself.  Roles can be a good base to define user account permissions.

### Resource

Resources are defined in different ways, depending on their need and ability to be accounted for specifically.  Every flow of any kind will reference a resource, represented either by ResourceSpecification or EconomicResource. Resource classifications also assist in understanding or finding a resource. More info at Resource concepts, Classification concepts.

#### vf:ResourceSpecification

This specifies the kind of resource, to the most specific level needed.  It also fills the space for the resource when it is not yet, or never will be, an actual resource.  It can be used in and across networks to communicate the resource type needed.  EconomicResource, as well as the resource concept referenced in flows (EconomicEvent, Intent, Commitment, Claim, RecipeFlow), conform to a ResourceSpecification.

#### vf:EconomicResource

An actual EconomicResource is created only by EconomicEvents.  It is also updated only by EconomicEvents for all its accounting related properties.  It becomes involved in a Process by being referenced by an EconomicEvent. It can appear on a Commitment or Intent if recording of a specific resource is needed.  It must have a ResourceSpecification.  It can have a stage and/or a state.  It knows its primary accountable Agent at any point in time.  It can be contained in another EconomicResource.

### Putting flows into motion...

More flow info at Flows concepts, Actions concepts, Processes concepts, Transfers concepts, Exchanges concepts.  First, some necessary pieces.

#### vf:Action

An Action specifies the type of flow and what the flow will do or has done. EconomicEvent, Commitment, Intent, Claim, RecipeFlow have an Action.  Actions are specified in Valueflows to cover the various ways flows affect resources.  Actions have properties defined that can drive the code logic to create or change EconomicResources when EconomicEvents are recorded, if desired.

#### vf:SpatialThing

Physical location, represented by SpatialThing, is mostly used as part of the information about agents, resources, and flows, although it can stand on its own if needed. It is primarily used for mapping. Although the relationships are not shown in the above diagram, the following are a SpatialThing: in EconomicResource, currentLocation; in Agent, primaryLocation; in EconomicEvent, Commitment, Intent, atLocation; and in EconomicEvent, toLocation.  When something has a non-physical location, it will use a different property. More info at Use of Other Vocabularies.

#### vf:Measure

Measure does not ever live on its own, it is a way to unify how quantities are represented in Valueflows.  Although the relationships are not shown in the diagram, the following are Measures: in EconomicResource, accountingQuantity and onhandQuantity; in EconomicEvent, Commitment, Intent, RecipeFlow, resourceQuantity, effortQuantity.  Measure is a numerical value plus a Unit. More info at Use of Other Vocabularies.

#### vf:Unit

It is very helpful for interoperaability that the same units of measure are used as networks communicate.  VF uses units defined by OM2, with some additional properties. More info at Use of Other Vocabularies.

### Flows in motion: Recipe

This set of Knowledge Layer entities together make a recipe for creating a Resource conforming to a ResourceSpecification. It can be used to automate generating a plan in the Plan Layer, since they follow the same basic input-process-output graph pattern. The recipe model may be made more complete in the future, to support forking, versioning, and variants.  It currently supports multiple recipes for the same ResourceSpecification.  It also supports a Recipe for more than one RecipeProcess in a flow graph, and RecipeGroup for creating a plan that includes more than one output from different Recipes.  More info at Recipes concepts.

#### vf:RecipeProcess

This defines a process node in the recipe graph.  A recipe can contain as many RecipeProcesses as it needs to produce the resource defined in the final ResourceSpecification. It can optionally conform to a ProcessSpecification.  It will have at least one input or output RecipeFlow.

#### vf:RecipeExchange

RecipeExchange corresponds to the Agreement in the Plan Layer.  It enables generation of plans that include agreements.  It can contain as many RecipeFlows as needed.

#### vf:RecipeFlow

A RecipeFlow defines either an input or output to a RecipeProcess, and/or a clause of a RecipeExchange.  RecipeProcesses and RecipeExchanges can be combined into one recipe if desired.  A RecipeFlow through its Action defines how it will affect the (resource of the) ResourceSpecification.  If it defines a ProcessSpecification stage, then the flow expects a resource at that stage of production.

#### vf:Recipe

A Recipe defines a way to easily tie all the RecipeProcesses needed to create an output.  If your Recipes have only one RecipeProcess, you may not need Recipe.

#### vf:RecipeGroup

A RecipeGroup makes it easy to include more than one output from more than Recipe in one Plan.

### Flows in motion: Planning

Planning can be done with or without recipes.  And planning is not always done, sometimes the economic activity is only observed, depending on the use case.  This section is about operational planning, proesses and agreements that are intended to be executed in this lowest level of detail.  More info at Planning concepts and Generation of Plans.

#### vf:Plan

A Plan is a collection of one or more operational Processes and/or non-process Commitments (such as transfers) in the input-output-process graph pattern.  Plans can also reference one or more Commitments that create the independent demand that provides the reason for, and final output of, the Plan. If the use case calls for it, Plans can be nested in Scenarios to give higher level views that drill down to operational Plans, or reference a Scenario that was done as a pre-planning effort.

#### vf:Process

This section talks about operational processes, see below for higher level processes.  A Process can exist both in the Plan and Observation Layers, or either one.  If it is planned, then observed as an actual process, it remains the same Process.  So it can have input and/or output Commitments, and/or input and/or output EconomicEvents.  It can also have input or output Intents, if all or some of its flows are not committed, but are intended to happen.  Processes are usually (but not required to be) planned within a Plan.  A Process can be based on a ProcessSpecification or not.

#### vf:ProcessSpecification

This specifies the kind of Process, to the most specific level needed.  Processes can be based on a ProcessSpecification.  It is also used as the stage of an EconomicResource that is created in stages, and is part of the logical identifier in those cases.  RecipeFlow and Commitment can have a ProcessSpecification stage specified to indicate that the resource they expect is at a particular stage, for example "tested" or "edited".

#### vf:Commitment

A Commitment is a planned flow.  It can be input or output of an operational Process or planned directly in a Plan if it is a non-process flow. It also can be defined as an independent demand of a Plan, meaning it is creating what the plan is for.  It can be a clause of an Agreement, even if also an input or output of a Process.  It references something to define a current or future resource, often a ResourceSpecification, but sometimes an existing EconomicResource if that exists and is important, usually because it is one-of-a-kind. Like all flows, it references an Action that defines its effects on the resource.  It can satisfy one or more Intents or be fulfilled by one or more EconomicEvents.  A Commitment references both a provider Agent and a receiver Agent, although it can be planned temporarily without both provider and receiver if there is a committed Agent assumed or immediately expected as part of planning. If it defines a ProcessSpecification stage, then the flow expects a resource at that stage of production.

#### vf:Agreement

An Agreement is a purposefully abstract term, so that it can represent many existing (or not-yet-invented) kinds of agreements, e.g. exchanges or income distributions.  Its main purpose is to contain related Commitments in planning, usually reciprocal commitments.  It can also be used to contain reciprocal EconomicEvents in cases where there has been no planning, such as point of sale.

#### vf:AgreementBundle

An AgreementBundle contains all the agreements bundled together for user purposes, for example multiple line items in an order.

#### vf:Intent

Intent is defined here as part of operational planning, but can also be key as part of a Proposal or part of a Scenario, see below for those uses of Intent.  An Intent has a provider or a receiver Agent, but not both. As part of planning, Intents can be entered directly or generated from recipe, as inputs or outputs to a Process, or as non-process flows, when there is no known Agent assumed to be the missing provider or receiver.  An Intent can be satisfied by one or more Commitments, and/or one or more EconomicEvents if the Commitment does not exist.  And as a flow, an Intent will have an Action. In operational planning, it will also reference a ResourceSpecification or EconomicResource.

### Flows in motion: Offers and Requests

Offers and requests are published primarily to look for a reciprocal match, although they can also be gift offers or requests. Common use cases are e-commerce, timebanks, mutual aid, price lists, publication of help needed for planned work in a network.  More info at Proposals concepts.

#### vf:Proposal

A Proposal is a container of related Intents, and is an offer or a request, determined by the purpose.  This also corresponds to whether the provider or receiver Agent is undefined in the primary published Intent. Proposals often have more than one Intent, either because there is a reciprocal Intent, or because more than one resource is being offered or requested together.  An Intent can be re-used in more than one Proposal.  A Proposal can be proposed to one or more specific individual or group Agents, or just be part of a scope where Proposals are published.

#### vf:ProposalList

A ProposalList contains all the proposals in a user-defined grouping, for example a price list.

#### vf:Intent

Intents that are part of Proposals can be more loosely defined than if they are part of a Plan, although planned Intents can also be part of one or more Proposals.  For example, the note is often used to explain some of the defined fields when the offers/needs application mostly supports just text.  But all Intents should have an Action, and either a provider or receiver Agent.

### Flows in motion: Observation

The Observation subject area is where economic activity actually happens.  The basic input-process-output graph pattern is again the same as for recipes and planning. More info at Flows concepts.

#### vf:Process

See the operational Process defined in the Planning subject area.  Operational Processes are carried down to the Observation layer as they are executed, or can be directly defined for Observation if planning is not done.

#### vf:EconomicEvent

An EconomicEvent is the "real" flow, one that actually happened.  Its behavior is governed by its Action.  It actually affects an EconomicResource if one is defined as inventoried and referenced in the EconomicEvent, possibly including quantities, location, primary accountable, stage, state, containment.  EconomicEvent has a provider and receiver Agent, and can be input or output of a Process, and/or part of an Agreement.  An EconomicEvent knows its resource, either an EconomicResource or a ResourceSpecification.  In some actions, for example transfers and moves, there can also be another EconomicResource on the receiver side.  EconomicEvents can fulfill a Commitment or satisfy an Intent (where there is no Commitment) or settle a Claim.  An EconomicEvent can correct a previous EconomicEvent, or reverse it completely.

#### vf:Claim

A Claim on another Agent is triggered by an EconomicEvent, according to rules agreed to elsewhere, although most EconomicEvents do not trigger a Claim, and if there is already a Commitment, a Claim is not needed.  The Claim then can be settled by other EconomicEvent(s).  As a flow, a Claim has an Action, provider and receiver Agent, and reference to a ResourceSpecification.

### Estimation and Analysis

More info at Estimates and Analysis concepts.

#### vf:Scenario

A Scenario is used as a grouping mechanism for flows.  It is a loose concept, and can support many situations.  It can be defined by a ScenarioDefinition.  It can contain Plans, Processes, Intents, aggregated EconomicEvents.  A Scenario can also be nested in itself, to support continued zooming out to less detail.  The uses below are some but probably not all of the possibilities.

#### vf:Plan

When Plans (which are operational) are nested in a Scenario, the Scenario can be used to zoom out for less detail in a UX.  When a Plan is a refinement of a Scenario, the Scenario was an earlier estimate or pre-plan.

#### vf:Process, vf:Intent, vf:EconomicEvent

When Processes are nested in a Scenario, they are generally higher level processes for aggregated as-is or to-be resource flows, for analysis or persuasion. Non-process Intents or EconomicEvents could also be part of these Process higher level flows.

Processes and/or Intents could also be nested when they are part of a budget, forecast, or other higher level pre-plan. Or with-list Intents might be listed, say for large many-agent barter, or when saved for future Proposals.

The agent vocabulary describes networks of people, organizations, and ecological agents, constructed using a simple but powerful model of agents and their relationships.

See also Agents in the Diagram Explanations and Agent examples.

## Types of Agents

Types of agents:

* **Persons** are human beings.
* **Organizations** include formal or informal organizations of all kinds. This also includes groups, as long as they consider themselves to have some agency as a group.
* The **ecological agent** concept is added to expand the scope of REA to do ecological and climate accounting, including impact of various resources on agents in the environment.

(The concept of "Agent" could also in the future include software/AI-based agents(bots, self-driving vehicles, etc.), but this is controversial and somewhat complex.)

In Valueflows, we are talking about economic agents, agents who can create or modify or exchange value, and make agreements with each other - who have economic agency.  Adding the Ecological Agent also expands the concept of "economic", bringing that kind of activity and impact, and even agency, out to the whole ecosystem, not just the human one.

If people want to define types of organizations (like cooperative, corporation, network, community, etc.) we provide a classification property which people can define as they wish.  We do the same for the ecological agent (like ecosystem, forest, etc.).

We have defined the properties of Agents very minimally. There are a number of useful properties in existing vocabularies, such as foaf, vcard, schema.org, and others that can be used. Or people can create their own as needed.

## Agent Relationships

Agent relationships have many nuances, thus VF provides the ability to define one's own kinds of relationships.  For example people might "participate" with an organization by means of agreeing to terms and conditions.  Or people might have more active "membership" in a group or organization.  Or people might consider themselves members but want a more independently flavored term such as "affiliates".

A relationship can be more like a role, for example "grower" or "harvester" for a food network.

Relationships have direction: For example, in "Michael is a member of Enspiral", Michael is the subject and Enspiral is the object.  In this case the inverse is also valid, "Enspiral has member Michael". In VF, we consider this to be one relationship.  One directional relationships like "follows" are also supported.

Relationships can be in a scope (or not): For example, "Kathy is mentor of Sam, in the scope of Enspiral."

EcologicalAgents and Organizations both need human Agents to act on their behalf and represent their agency in the world of people. This can be defined as various roles.

## Network Shapes

Different kinds of relationships can be thought of as creating the "shapes" of a network. Something like this:

The following shows some agents that are "inside" a network, also some agents that are "outside" a network, but have relationships with the network agent or with agents within the network.

## Agent Philosophies

We also want to acknowledge that some people prefer to think of themselves as independent and decentralized agents who interact in different places in the economy as individuals, and some people think of themselves more as members of different groups and networks and communities and interact more in the context of those groups and networks and communities.  Many experiments are going on as people strive towards another economy.  We want to support all these experiments, so want to support both of these ways of thinking and organizing ourselves.  The agent vocabulary is very flexible, and will support these as well as current conventional structures.

So, if people want to form a group that has agency as a group, fine.  If people want to consider that their group does not have agency as a group, also fine.  Not all groups, and especially not all networks, will be economic Agents in Valueflows. That depends on the agreement of the people in the group, and what the group needs to do as-a-group. For example, does the group need to make agreements as-a-group with other groups? Or exchange resources with other agents as-a-group?  Note that within the vocabulary, network formations will emerge, as agents have economic interactions with each other in the world.  This does not mean that the network is necessarily a Valueflows Agent, but it could be, if the participants want.

The resource vocabulary describes resources and types of resources, defined broadly.  They can include useful goods and services, digital documents and representations, code, money, tokens, credits, energy, work, skills, CO2, methane, heat, air, water, soil microbiota....

See also Resources in the Diagram Explanations, Actions, and Resource examples.

## Definition

Traditionally, an economic resource is defined by its utility, but also by its scarcity and its control by an economic agent. That definition is based on accounting for private ownership, and we believe is too limited.

* Intellectual creations like designs are not scarce, yet they clearly are economic resources. They only become scarce when legally restricted by patents, licenses, and copyrights.
* Air, water, and other products of nature are clearly economic resources, but they are not under the control of an agent unless they are legally restricted by ownership. However, by means of the invisible foot that accompanies the invisible hand, they are regularly degraded by enterprises, and not accounted for, classified as “externalities”.

We want to think of ourselves as participants in ecosystems, not competing enterprises. As such, we need to account for our effects on all aspects of our ecosystems.

And we want knowledge to be freely available.

Also, we prefer to think of use value, but economic resources also often have exchange value.

### The difference between a resource and its specification/classification(s)

An economic resource is observable.  Its specification or classification defines what kind of thing the economic resource is.

So, for example, most listings of things offered for sale on an e-commerce site are specifications, which can be searched using classifications. The one in a box delivered to your door is a resource.

Or the description of the book entitled "The Power of Babel: A Natural History of Language", ISBN-13: 978-0060520854,
is a specification. Your library may have two copies that you can check out. Those are resources.

### The difference between a resource specification and a resource classification

An economic resource or a flow can have only one *resource specification* in Valueflows.  This defines the lowest level useful type or kind of the resource that is needed. The Valueflows vocabulary defines this as the ResourceSpecification.  Note that often taxonomies and other references on the web can define very specific resource specifications at their leaf levels, and these can be used if the necessary properties can be found.

An economic resource or a flow can have any number of *resource classifications*.  They are used to filter, match, or group economic resources.  Resource classifications can be part of a taxonomy. That means they can be defined very broadly and generally and maybe vaguely, or they can be defined very narrowly, but fit into broader classifications.

So, for example, Herb might be the parent classification of Anise Hyssop, Goldenrod, Nettles, Red Clover, etc.  Besides its usefulness in understanding taxonomies of resource types, this can be useful when one can define a general recipe that will work for many more specific kinds of resources.

People can use the multitude of existing taxonomies for resource classifications, or can also create their own as needed.

Resource classifications can also use other schemes, like facets or tags.  It is left vague in order to be flexible.

The references to resource classifications are uri's, and not otherwise defined inside Valueflows.

## Identification and Behaviors of Resources

Here are three different kinds of resources from the viewpoint of identification:

* serialized resources, where each individual instance has a unique identifier,
* lot-controlled resources, where each lot or batch has a unique identifier, but the lot or batch may contain many individual instances, and
* count or volume or stock resources, where individual instances are indistinguishable, or in the case of fluids, only exist on a molecular level.

Serialized resources would fit the direct identification pattern. Lots can be split up, so the identification of a subset of a lot would require some other properties, such as location. Stock resources can only be described indirectly, by means of some combination of properties, such as specification and location. (Location is a complex ontology of its own: for example, in warehousing, a location is often composed of warehouse:room:aisle:row:tier.)  The tracking identifier is used for serial numbers.

Moreover, identification of resources will depend on scope and purpose. We want to allow each scope or context to define resources that they have relationships with, according to the combination of properties that works best for them, which might include which agent has which relationship with a resource.

And then in the "independent view", for larger-scale analysis of resource flows, or for example for lot tracking for public health issues like mad cow disease, different combinations of properties might be needed.

### Substitutability

This defines if any resources of that specification can be freely substituted for any other resource of that same specification when used, consumed, traded, etc.  For example, one container of "B9R-1-red DLP resin photopolymer" is probably substitutable for another container of the same photopolymer.  While each resource for a resource specification called "English-Spanish translation" is probably not substitutable because each will be a different document.

### Unique identifiers for resources

This can vary.  And people can be allowed within some boundaries of agreement to specify which combination of other properties would constitute identifiers.

Here are some examples from manufacturing situations:

* Unique identifier = an assigned serialized identifier, which is unique across manufacturers, due to agreements in an industry.  Examples are computers, vehicles, and other equipment.
* Unique identifier = resource model + lot identifier + location + owner: so in other words, the owner of the rights was part of the unique identifier of the resource, and if the resource got transferred from one owner to another, the first owner's resources would be decremented, and the second owner's resources would be incremented.

Note in the last case, a transfer of rights means a different resource. This is common with resources that are not serialized, where one logical resource has a quantity greater than 1, and the individual instances are substitutable. (Think nuts and bolts, grain, strawberries, bottles of beer in cases, etc.)

### Stage and state

Sometimes part of the logical identification of a resource includes:

* *stage*: the ProcessSpecification of the most recent process the resource was output from, such as "test"
* *state*: the state of the resource on output from a process, such as "failed"

Stage is used when the same identified resource passes through multiple processes in its lifetime, and that information is needed by the next process to determine which resources can be valid inputs.  For example, in creating a translation, you might have one translated document pass through translation, editing, proofreading, and formatting stages. You don't want to bring that resource into the formatting stage until it has been proofread, for example. Or you might have a testing stage for a component or product, in which case you don't want to consume or transfer the resource until it both has been through the testing stage, and had a `pass` output state.

These can be defined on the recipe or the plan, showing where an input flow expects a certain stage and/or state of a resource. In that case, Dependent demand planning will select only those resources that fit the specified stage and state.  In user-interface forms for adding process input EconomicEvents, if the use case uses stages, the input event form should query EconomicResources for required stage and state when offering selections of possible input resources.

An alternative to using staged resources is to have different resource specifications, and therefore different identified resources at each stage.  This eliminates the extra complexity of the stage model, but also means you can't tell that the same resource is passing through stages.

### Inventory

Economic Resources can be inventoried, not inventoried but could be, or it doesn't make sense to think about inventory.  If a resource is not inventoried, it is generally not instantiated in the software, but defined using resource specification and other properties, such as the accountable agent or location.

* Inventoried: You want to keep track of it, its changes in quantity, and how many you have right now.
* Not inventoried: You could keep track of it, but it isn't worth it.  This usually happens for quantities of small or hard to measure items that are obtained in bulk, like solder or bolts.  In this case, you have to look at the actual resource to see if you need more, the data won't tell you.
* Not applicable: This is for types of work (unless scheduled), services, and other resources where it just doesn't make sense.

## How resources relate to events

In the original REA ontology, an Economic Event is a change in the quantity or in the rights to an Economic Resource performed by Economic Agents. An event is also defined by its behavior in relation to the resource  (consume, use, produce, transfer, etc.).

Some people use the terms "stock" and "stock flow".  A stock is a resource; a stock flow is an event. (The term stock is too limiting, since a resource could be digital, like a document or media file.)

An event can trigger incrementing or decrementing a resource.  Sometimes it does neither, as in the case of using a piece of equipment or citing a document.  But in any case, the quantity of a resource related to the event is not a resource itself, it is just a property of the event.  For example a resource could be 100 widgets on a pallet, lot number 1234.  If 10 of those widgets are consumed in a process that makes something out of them, that is an event: consumption of 10 widgets of lot number 1234.  The 10 widgets are not a resource in their own right.  The event triggers the decrement of the original resource of 100 widgets, which now has quantity of 90.

For serialized or uniquely identified resources, if the logical and technical unique identifiers are not changed by an event, such as moving a vehicle to another location without any changes to its accountable agent (and assuming location is not part of the logical identifier), the resource does not behave like a stock and is not decremented or incremented.

All economic information in an Economic Resource must be put there by an Economic Event.  Non-economic information (note, image, etc.) can be updated on the Economic Resource directly. Economic information is anything that might affect periodic accounting or financial reporting.  In this way, there is always an immutable detailed time-based record of information that affected such reporting.  And there are not excessive economic events for only non-economic updates.

Note that the economic information is therefore derived information, and could be re-calculated as needed by iterating through the Economic Events. But that could have performance issues, so isn't generally recommended.

## How resources relate to transfers

Two different kinds of "inventorying" of resources are affected by transfers.

* quantity of the resource where the agent has full (human realm) rights and responsibilities, irrespective of custody
* quantity of the resource where the agent has custody or physical possession, irrespective of rights, more of an operational focus

We define two current quantities on the economic resource for these two concepts, *accounting quantity* for the first and *onhand quantity* for the second.

For example, in vendor-managed inventory, the vendor owns the inventory so they see it in their accounting; but the store sees it in their onhand quantities. Or for inventory being shipped FOB source, the intended receiver owns the inventory and sees it in their accounting, but the goods are actually onhand in a truck.

See also the Transfers concepts.

## How resources relate to each other

If one resource contains other resources, the contained resources are part of, or make up the larger resource.

For example, a bank account might contain a number of "virtual accounts" that a group manages itself, outside the bank's knowledge.  Or, a tool maker might make several different kinds of tools, which they treat as separate resources; but they might package some of those into a tool kit, also a resource.

Value flows (you could also call them resource flows) are a fundamental construct in the Valueflows ontology. They put the economic activity into motion.

See also Actions, Core Concepts, Processes, Transfers.

## Kinds of Flows

The types of flows form a progression from defined to  potential to scheduled to realized.

### Recipe Flow

Recipes are used to create plans, and the Recipe Flow can create a corresponding Intent or a Commitment in a Plan, depending on if all the agents are known and the level of certainty of the planning.  See also Recipes, Planning from Recipe, Flows in motion: Recipe, Planning from Recipe example.

### Intent

Intents describe potential future events which have not been agreed to by other agents, such as offers and requests. Intents are often used for discovering another agent to participate in a desired event. On the process side, for example, planned work could be an Intent, but planned work that some agent committed to do is a Commitment.  See also Offers and Requests, Flows in motion: Offers and Requests, Offers and Requests examples.

### Commitment

Commitments describe potential future events which the involved agents have already agreed to pursue. Commitments can be considered contractual promises from one agent to another.  Commitments can be thought of as plans for Economic Events, and Economic Events can fulfill Commitments.  Commitments can satisfy Intents.  See also Operational Planning, Flows in motion: Planning, Planning examples.

#### Possible gray area between Intent and Commitment

When making an operational plan, where there isn't really a question of some agent stepping up to commit or being assigned, and no published Intent is needed, then Commitments can be used, even though there may not be an agent committed yet. The criterion can be thought of as firmness of plan, not commitments of agents.  Basically, sometimes making a plan takes some time, so during that activity, if Commitments are not assigned, it is OK, better than adding unnecessarily to the machinery needed to make a plan by using Intents.  On the other hand if publication of the flow is needed to find an Agent to commit, then an Intent is better, as it can become part of a Proposal.

### Economic Event

Economic Events describe past events, something observed, never some potential future event.  They can fulfill Commitments or satisfy Intents (when there is no Commitment).  See also How Resources Relate to Events, Flows in motion: Observation, Production examples, some of the Transfer and Exchange examples.

### Claim

Claims resemble Commitments, but are initiated by the receiver, not the provider.  If there is not an existing Commitment, an Economic Event can trigger a reciprocal Claim, based on an agreement.  Even then, Claims sometimes do not have to actually be instantiated, often they can be implied from an Economic Event and an agreement.  For example, if Alice has agreed to sell Bob some carrots for $2, then if Alice delivers the carrots to Bob, she has an implicit claim for $2 from Bob.  See also Flows in motion: Observation, Claim example.

## Timeline, plans and observations

The figure below shows that Economic Events have to be observed and for that reason only appear as records of the past. Future plans get represented with Intents and Commitments.

## Matching Intents

Often agents will start their plans independently and record their initial intents. Later once they make a Commitment with another agent, it will represent a specific shared part of their plans. For that reason any Commitment can result in Satisfaction of the providing agent's Intent as well as Satisfaction of the receiving agent's Intent.

## Granularity

Intents, Commitments, and Economic Events can occur at any granularity that is needed or for which data can be obtained.  So they primarily are used for all operational needs, but can also be used at higher levels for budgeting for organizations, analytical and high level planning needs for communities or regions, etc.

Any flows that are part of a Plan are operational, defined at the lowest level.  Flows that are part of a Scenario are not operational.  They could have many uses, from pre-planning to higher level analysis, but are not considered part of any scheduled planning for what will actually occur.

## Actions

All types of flows use the same set of actions, which define what the flow does and how it behaves in relation to resources.  You can find detailed documentation on actions on the Actions page.

## Quantities and Times

Quantities are used for counting, such as:

* Exchange/transfer
* Resource increment and decrement
* Recipes, how much or many goes into and out of a transformation process

Times are used for coordination and scheduling, such as:

* Calendar availability
* Planned timelines

They can be used together for analysis and reporting, such as:

* Accounting totals (quantity) within accounting period (time)

Quantities can be any needed unit of measure, including counts, volumes, weights, etc.  Time can be a beginning/end time (an interval), or a point in time, or a due date.  The flows require at least one of those.  If a point in time is recorded, an application should return that time as the beginning and end time if asked.

Note that recipes may need to scale both quantities and calendar times when used to create a plan.

Sometimes a quantity is expressed in time-based units, like "I worked 6 hours", or "we used this machine for 8 hours".  These flows also may have a related time, like "I worked from 10am to 4pm", or "we used this machine from 8am to 4pm". In these examples, the quantity is used for accounting figures, exchange, recipes.  The time is used to schedule and coordinate the work or machine usage.

Sometimes a situation may call for a "compound quantity", like "Number-per-Year".

See also at Use of Other Vocabularies.

## Correcting Events

Economic events are immutable in accounting practice, since at any time they could have been reported formally.  To correct economic implications of an economic event, you need another economic event, which can be related to the first one with the relationship `corrects`.  The correcting event can have a negative number.  It can either completely back out the original event or adjust it.  See also Making Corrections on the Accounting page, the Correcting Errors example.

All flows (Economic Event, Commitment, Intent, Claim, Recipe Flow) use an action property to designate what the flow is doing and how it will affect or has affected an economic resource (or not).

See also Flows and Economic Resources.

The actions contain data that defines how they will behave relative to a user interface, and relative to the effects on economic resources.  This enables the behavior to be data-driven if desired.

## Action Definitions

We have defined a core set of actions, but expect that this will be extended with some others. If extended, we recommend that they be defined as part of this or another formal vocabulary so that all can use them and assume the same meaning.

**produce** - A new resource is created in the process, or an addition to an existing stock resource of the same type is incremented.  `produce` is used in manufacturing of goods, but also in any kind of creation of a material or digital or energy resource.

**consume** - Most often, an ingredient or component is transformed  into the output(s) of the process. Or the input resource can be just used up during the process, like energy. After the process the specified quantity of the consumed input is gone.

**use** - Most often `use` is employed for equipment or tools that are used in a process, but not consumed.  After the process, the piece of equipment of tool still exists, but during the process, it is unavailable. The unavailability can be useful to know if the resource must be scheduled, or if one needs to know how much the resource is used.

**cite** - `cite` is used when a resource is input to a process, but is neither used nor consumed, and remains available during the process.  Examples are a design file or a scientific paper, any digital knowledge, which is cited so that the agent(s) responsible for the resource receive credit.

**work** - `work` refers to labor applied to a process.  There is generally no identifiable resource involved, only the provider agent. In this case, the type of work or skill involved can be identified by a resource specification. A possible exception would be if the agent's work schedule is kept on a calendar, representing when the specific agent is available to work.

**pickup** -  The transported resource or person enters the process; the same resource will appear later in an output of the process.

**dropoff** -  The transported resource or person leaves the process; the same resource or person appeared in an input of this process.

**accept** - This is used as input to a process involving repair, modification, testing, or similar of a resource.  The same resource will appear in the output of the process.  It is sometimes a bit of a gray area when to use `accept`/`modify` vs. `consume`/`produce`.  The choice is based on the need to have the same identified resource before and after the process. Generally if the resource is involved in a series of processes to create it before anything else happens to it, `accept`/`modify` is appropriate.  If the input resource and the output resource need to be identified as different resource specifications for any reason, then `accept`/`modify` is not appropriate.

**modify** - The identified resource that was accepted into a process appears in the output of that process, with modifications made.  Note not all modifications require a physical change, for example quality testing.  In all cases though, it matters that the resource has gone through that process, and the `stage` of the resource (the process specification of the process) is then used as part of the logical identification of the resource when the resource is requested as a process input or for a transfer.

**combine** - A resource is put in a package or a combination resource; the same resource might appear later when it is separated.  Examples are packing one or more resources for transportation or storage, or creation of a kit resource.  The combined resource is still identified in the system, but is `containedIn` the package or combination resource, which would be usually produced in the process.  When a resource is `containedIn` another resource, it is not available on its own.  Note that packing materials or containers which will continue to have their own identity later are also combined in the process; if not, they can be consumed. Note also that it doesn't make sense to combine a resource, for example a digital resource, if that resource can in fact be acted upon while combined.

**separate** - A resource is removed from a package or a combination resource; the same resource appeared as input earlier in this or another process when it was combined.  When the resource is separated, it loses its `containedIn` reference, and becomes available on its own.

**deliverService** - A new service is produced and delivered as output of a process. A service implies that an agent actively receives the service at the same time as it is delivered.  Services are not tangible, so would not create or increment an inventoried resource. Services are perhaps most often delivered directly to an agent. But unlike other actions, sometimes the service is at the same time being delivered into another documented process, in which case it can be output from a process and input to another, at the same time.

**transferAllRights** - This action gives full (in the human realm) rights and responsibilities to another agent, without transferring physical custody.  People might call this "ownership"; or it might be considered "stewardship" or similar.  This occurs instantaneously, and does not involve documented physical transfer.

**transferCustody** - This action gives physical custody and control of a resource to another agent, without full rights. The physical custodian often has responsibilities associated with custody, however.  Examples where transfer of custody is useful are loaning a resource to another agent, or when a resource is transferred to have a service performed by another agent, like transportation or repair.

**transfer** - This action gives full (human) rights and responsibilities plus physical custody, combining the last two actions for simplicity.

**move** - `move` changes the location (and possibly the identifier, if location is part of the logical identifier) of a resource, but does not transfer agent rights or custodianship.

**copy** - A new resource is created for the receiver, an exact copy of the original provider resource, used for digital resources.

**raise** - This action adjusts a quantity up, used either when a computer system is brought up and existing resources must be entered with a beginning balance, or when an inventory count in the real world shows that the quantity in the computer system is too low.  When it is known how a resource was obtained, it is preferable to use the real action.

**lower** - This action adjusts a quantity down, used either when a computer system is brought up and existing resources must be entered with a negative beginning balance (very rare!), or when an inventory count in the real world showing that the quantity in the computer system is too high.  When it is known how a resource was lowered, it is preferable to use the real action.

## Action Behaviors

The behaviors that are included on the tables below are also defined as Action properties so that computer systems can be "data driven" in this respect if desired.

### Event Effects

**eventQuantity** - Either only `resourceQuantity` or only `effortQuantity` or both make sense on an economic event with this action.  The action `use` provides for both because there can be a requirement for use of some number of a resource (or resource specification) for some time or other effort unit.

**inputOutput** - An event with this action can be `input` of a process, or `output` of a process, or should not be related to a process.  The event with the special case `outputInput` is basically an output of a process, but can sometimes also be an input to another recorded process, at the same time as it is an output.  This is because services imply delivery as they are created.

**pairsWith** - These pairings indicate that events with these actions will be input and output of the same process, and imply reference to the same economic resource.

**createResource** - An event with this action generally should support the options to create a new resource or to increment an existing "stock" resource. This will be a choice the user (or possibly specific application rules) must make, there are no rules defined in the vocabulary or data, and it depends on what actually is done operationally, and how agents choose to identify and manage their resources. It is also possible that neither will occur, if the agent does not inventory this particular resource for whatever reason.  If a resource is created by the actions with `optional`, it is the `resourceInventoriedAs`; if with `optionalTo`, it is the `toResourceInventoriedAs`.  

Note: Any action that can create a new resource can alternatively affect (almost always increment) an existing "stock" resource. 

### Resource Effects

**accountingEffect** - If there is an inventoried resource, this defines how the economic resource's `accountingQuantity` is affected by the event's `resourceQuantity`.

**onhandEffect** - If there is an inventoried resource, this defines how the economic resource's `onhandQuantity` is affected by the event's `resourceQuantity`.

For both AccountingEffect and OnhandEffect, the main options are `decrement` (subtract from), `increment` (add to), or no effect. For actions with the option `decrementIncrement`, the `resourceInventoriedAs` should be decremented (if there is one);and the `toResourceInventoriedAs` should be incremented (if there is one).  For actions with the option `incrementTo`, the `toResourceInventoriedAs` should be created/incremented, and the `resourceInventoriedAs` should be left as-is.

Note: The event's `effortQuantity` does not affect economic resources.

Note: The actions `use` and `work` are time-based actions, either with or without an explicit schedule. Although not defined in VF, if a calendar schedule is documented as connected to the economic resource, then those economic events could possibly "decrement" that calendar schedule in some way.

**locationEffect** - For this action, if the economic event's `toLocation` exists, then the affected economic resource's `currentLocation` should be set to the same location.  For `new`, the resource's location should be set only if it is a new resource.  For `updateTo`, the resource is the one in `toResourceInventoriedAs`.  For `update`, the resource is the one in `resourceInventoriedAs`.

**containedEffect** - This applies to the actions that deal with resources contained in other resources, and applies to the `resourceInventoriedAs`.  The `update` option sets the resource's `containedIn` resource, which can be referenced in the event's `toResourceInventoriedAs`; the `remove` option nulls the resource's `containedIn` resource.

**accountableEffect** - If there is an inventoried resource, these actions should set the resource's `primaryAccountable` agent using the event's `receiver` agent.  For `new`, this applies to new resources created by the event (otherwise the `receiver` and the `primaryAccountable` should already match).  For `updateTo`, the resource updated is the `toResourceInventoriedAs`.

**stageEffect** - For actions with `stage`, if the process which the event is output of is based on a process specification, set the `stage` of the `resourceInventoriedAs`, or of the new resource if one is created, to the process specification.

**stateEffect** - If a resource is created or updated by the economic event, if the `state` is included in the event, set the `state` of the resource to the event `state`.  If `update` the resource is the `resourceInventoriedAs`; if `updateTo` the resource is the `toResourceInventoriedAs`.

### Behaviors by Action

*To make the diagram bigger, you can right click and select 'View Image' or 'Open Image in New Tab' or a similar command in your browser.*

*In the above chart, the `notApplicable` values are not included, for easier overall viewing.  For the complete list of behavior values by action as defined in the rdf vocabulary, see the turtle file starting at the Actions section.

### Implied Transfers

Implied transfers can happen when the provider and receiver agent are different.  The transfer (or transferCustody or transferAllRights) behaviors and implications should be applied in addition to the behaviors and implications documented for the non-transfer action. See Implied Transfers in Concepts for details.

### Saving Breadcrumbs for Track and Trace

If you will be using the track or trace algorithms to find the connected value flows forwards or backwards when there might be repeated processes, an additional field is needed when saving an event.  See Breadcrumbs in the Track and Trace algorithm for the procedure.

# Processes

By Process, we mean an activity that transforms inputs into outputs. The outputs might then become inputs to other processes, forming networks and chains. Those chains may be circular, where an output from one process becomes an input to another process that occurred previously in the same chain, supporting circular economies.

Process spans the Plan and Observation layers.  I.e. intents, commitments, and economic events can all be connected to the same process as it moves through planning and observation.

See also Input-Process-Output in the introduction, Flows in Motion: Planning and Flows in Motion: Observation in the Diagram Explanations, Production examples, Planning examples, and Community planning and Regional analysis in the Scenario examples.

## For example...

* For example: a farming process takes compost, soil, seeds, water and human and mechanical work as inputs, and transforms them into grains, nuts, fruit, and vegetables. Those ingredients may go to kitchens that create dinners for people to eat. Some of those ingredients may be pared off in preparation, or spoil, or be left on plates. Those leftovers go into compost, which starts the process chain over from the beginning.

* Or for a bad example: a CAFO (Confined Animal Feeding Operation) produces a lot of manure. They put manure into big lagoons, which drain into the water table, and come back up in people's drinking water, causing diseases, for which the people become inputs to hospital processes.

  * One of the inputs to the CAFO process is antibiotics. The animals are filled with antibiotics because they get sick in the CAFO environment. And the antibiotics are also an output, mixed in with the manure and meat.

  * The antibiotics then breed resistant bacteria, which end up in the people, and send them to the hospital, and then kill the people, because the common antibiotics no longer work. And the resistant bacteria remain in the hospital to kill other people.

Connected processes enable us to see cause and effect, if we want.

## Process structures

Process-based flows can create "directed graphs" in infinite combinations.

## Co-products and by-products

Usually processes have one output, but not always.  Sometimes there are co-products that have somewhat equal value.  Sometimes there are co-products that provide something useful, such as plastic shavings being put back into the melting pot for continued production as input.  Sometimes there are unintended by-products, resources that are known but not useful or are harmful.

Valueflows does not distinguish between "good" and "bad" resources created by processes, as that is conditional and can be subjective. On the other hand, this pattern gives the opportunity to record and understand harmful "externalities" from producing and transporting resources.

# Transfers

See also Flows without processes in the Core, How resources relate to transfers, and the Transfer and exchange examples.

## Transfer concepts

One concept of transfer is an activity that re-assigns rights for an economic resource from one agent to another.  A second concept is an activity that operationally changes physical custody or possession of an economic resource from one agent to another, without affecting rights.

Note that a transfer is a one-way activity.  Two or more reciprocal transfers form an exchange, and are connected in Valueflows by an Agreement.

We think that now, and more so in the future, there will be more gradations of rights and responsibilities for resources than are sometimes considered now.  For example, as a society we may decide that we should take more responsibility for recycling or upcycling resources at the end of their useful life for us, or not wasting them.  The concept of "ownership" may transition more into "stewardship" in a concept of the world that does not put humans in a position of controlling the world's resources or abdicating responsibilities to the ecosystem in the name of ownership.  So, we are for the most part avoiding talking about ownership in this vocabulary, or any of the possible gradations and combinations of rights and responsibilities, leaving the concept of rights flexible.

## Transfer examples

* For example, perhaps some agent has many apple trees, and plans on pressing apple cider. Another agent has an apple press and agrees to transfer use of the press (a resource).  The agent with the trees might transfer a portion of the apple cider to the agent with the press.  The use of the press involves some rights (to use the press for some period of time) and responsibilities (to not run it beyond its capacity and to clean it up before returning it).

* Or in a library, a book can be checked out, a transfer of custody from the library to the reader.  The agent who checks it out can read it and is responsible for caring for it and returning it on time, another transfer of custody.

* Or let's say that a community has farmland and equipment held in common.  The community transfers custody for the land and equipment to some farmers to use and take care of.  The community also transfers seeds every year to the farmers, enough to grow the food the community needs.  During the year, the harvests are distributed (transferred) to the community members for their consumption.  In reciprocity, the community provides for other needs of the farmers (transfers resources).

*Implementation note*: Different networks may choose to handle namespaces and identifiers at different granularity.  This also may depend on the technology used.  So one network may have separate namespaces for the nodes in the network; another may have one namespace for the whole network.  In the latter case, an implication on transfers is that the provider agent and the receiver agent may use the same resource identifier for `resourceInventoriedAs` and `toResourceInventoriedAs`, even though the primary accountable has changed.

## Explicit and implied transfers

In Valueflows, several actions can involve the transfer concepts and behavior.  (For more detailed information, see the Actions page, especially the Behaviors by Action.)

The explicitly denoted transfers are:

* transfer all rights (primary accountability: ownership, stewardship, etc.)
* transfer custody (only the physical custody or possession)
* transfer (shorthand for both rights and custody, since they often go together)

Some other actions can imply a transfer of all rights, a transfer of custody, or both.  This shortens and sometimes simplifies the flows.  But it is not at all required, it is fine to have separate transfer flows if that makes the use case more understandable.  The Transport with Transfer example illustrates this.

The way to imply a transfer is to designate a different provider and receiver.  It is not always true the other way though, a different provider and receiver does not necessary imply transfer behavior, usually because there is not an inventoried resource.  See also Exchanges and flows.

The following actions imply a full transfer of all rights and custody, when there is a different provider and receiver.   The implication is that any behavior rules of the primary action plus the transfer action are implemented.  And also the flow can be included in an agreement, for example paying for consuming a resource provided by a different agent in the receiver's process.

* consume, produce

The following actions imply transfer of custody only, when there is a different provider and receiver.  Since the implied transfer is only custody, this would normally not be used as part of an agreement.  But the behavior rules of the primary action plus the transfer of custody would be implemented.

* pickup, dropoff
* accept, modify

These examples that might help provide clarity: Transportation with Transfer, Checkout book, Claim for income.

See also an Exchange diagram in Core, Flows in motion: Recipe, Flows in motion: Planning, Flows in motion: Observation, also the Exchange examples.

## The independent viewpoint

Here we look at exchanges of resources from an independent or neutral viewpoint (not the viewpoint of one of the Agents in the exchange). For example, from one Agent's viewpoint, the exchange may be a Purchase, from the other Agent's viewpoint, it might be a Sale. From the neutral viewpoint, it is an exchange of resources, with usually at least two flows of resources, from different directions. So for example, the seller might give some goods to the buyer, and the buyer might give some money to the seller. Or in a barter exchange, one agent might give the other some books, and the other agent might compensate with some cookies.

Exchange is ubiquitous on the internet today, with offers everywhere. In Valueflows, we track not only the offers and promises, but also the actual flows of resources in networks, in all directions. And we support exchanges that don't involve money as well as those that do.

Valueflows enables multilateral exchange agreements as well. Any number of agents can commit to flows where they provide something and flows where they receive something. This way creating a reciprocal cycle in the flows graph. So for example, Alice can provide apples from her orchard to Bob, who can provide accommodation to Claire, who can provide tutoring to Alice's children. Such exchanges can happen in infinite number of possible ways, as long as all agents participating agree on specific reciprocal cycle in the flows graph.

We also support non-reciprocal one-way transfers, such as in a gift economy.  However, an exchange implies at least two transfers with reciprocity.

## Exchanges and flows

Exchanges as modeled in VF actually are reciprocal flows, not resources directly.

* For example, most timebanks exchange work for credits.  The work event can be part of a process that produces something for some other agent.  It is also part of an exchange in the timebank.  The transfer of credits on the other hand, is not part of any process that creates or transports something, it is merely the timebank recording that one account was decremented and another account was incremented.

* Exchange of work also happens in open value networks, where people record work events as input to many processes, and then when income is received for outputs of that work, people receive part of that income, in exchange for their work.

* Another example is when a service is created as an output of a process, where that service delivery event can be considered an implied transfer, and exchanged for some other resource.

To be included in an exchange, a flow must have a different provider agent and receiver agent.  Flows involved in transfers of rights to an inventoried resource are most obvious.  Other types of flows can also imply transfer behavior, and can thus be used as part of an exchange, such as consume and produce.  And yet other types of flows do not involve an inventoried resource, but still can be included in an exchange, such as work, delivering a service, or usage of some equipment.  Some types of flows don't make sense to include in an exchange, because there is only a transfer of custody involved, such as pickup and dropoff, or accept and modify. For more details see Explicit and implied transfers.

## Agreements

An Agreement can encompass a promised exchange, or an observed exchange without the promise.

Various kinds of agreements between agents often define the rights and responsibilities for economic resources that are transferred. Agreements can reflect any economic paradigm, so make it possible for the Exchange and Transfer vocabulary to work equally well for capitalist businesses, transitional economic interactions, and next economy interactions.

Agreements can be of any kind and scope, from an order to an agreement in a contribution-based economy to a larger blanket agreement.

Agreements can be combined into an Agreement Bundle.  This can be useful for example when each "line item" in an "order" needs to have a line item reciprocal commitment (like a "price"), instead of one combined reciprocal commitment for several primary commitments.

Valueflows does not define the detailed internal vocabulary for agreements.

##  Recipe exchanges

Recipes can include patterns for exchange, as well as production.  The Recipe Exchange is used to generate an agreement(s) and reciprocal commitments when a plan in created from the recipe.

# Offers and Requests (Proposals and Intents)

Proposals are published requests or offers, sometimes with what is expected in return.

See also Intents and Matching Intents in the Flows concept page, Flows in motion: Offers and Requests in the Diagram Explanations, and Offers and Requests examples.

##  How proposals work

Proposals are everywhere in advertising.  But we see many groups posting proposals that are different from commercial advertisements, such as timebanks, mutual aid groups, commitment pools, people working together on a project and looking for help, groups looking for donations, supply chains seeking specific offers from suppliers in their network.  All of these are supported, including commercial advertisements.

A Proposal has one or more primary Intents, and optionally one or more reciprocal Intents. The proposal has to do with the publishing of the intents, which have the actual content.  An intent can be published in more than one proposal, for example over time, or with different reciprocal intents like wholesale and retail price lists.  Multiple primary or reciprocal intents on one proposal imply an "and", like a Community Supported Agriculture (CSA) group might offer weekly veggie boxes, and in exchange want some money plus some work contribution on the farm.

Proposals can be grouped into Proposal Lists, for example for price lists.

Proposals can stay directed to a broad or specific *audience*. In the broadest case, they stay available for anyone (public proposals). In the most narrow case, the stay available only for specific agent. In between those two extremes a whole spectrum exists.  For example two distinct proposals can exist on providing particular product or service - one for club members and one for general public etc.

## Matching offers and requests

Proposals may be specific or more general, often not commercial at all, expressed not in identified products but in classifications and text.  But they want to find each other. The offers want to find the matching requests. The requests want to find the matching offers.

When they find their match, those with the matching offer and request enter into a conversation which might result in an agreement, starting a cycle that ends with observed transfer or exchange.

Agreements, which are committed to by agents, can evolve from proposals directly, or conversations about proposals, or be entered into without proposals.  Besides agreements, a proposal to do something might trigger a conversation which could result in commitment for an input(s) to a process, with or without an associated exchange agreement.

These types of conversations may lead to more and better cycles of engagement.  Valueflows does not at this time define the pattern of this kind of conversation, but intends to integrate with different social networking vocabularies for this purpose.  We do think that social and economic networking are naturally intertwined in human behavior.

An operational plan is a schedule of related operational processes, that constitute a body of scheduled work with defined deliverable(s).  A plan normally contains one or more process resource flows, one for each deliverable.  It can also contain the reciprocal agreements expected for different involved agents involved in the flows.

See also Flows in motion: Planning in the Diagram Explanations, Generating plans from recipes, and the Planning examples.

## Coordinating work

A plan can cover more than one scope, if the different scopes are tightly coordinated with pre-agreed rules, for example sub-organizations of a main organization, or an ongoing supply chain.  If not, or if the agents prefer, then requirements from one scope could become deliverables for another scope's plan.  Different batch sizes could trigger a new plan for inputs to the main deliverable too.  But all of this does not affect the vocabulary or model.  Plans can relate to each other through resource flows just like processes.

Plans are used for understanding and coordinating what needs to happen for specific outputs. The size and complexity of a plan is up to the people who are planning and coordinating the work.

A plan can be generated from a recipe, or created without one.

Some examples:

* A communications group creates articles for a larger group. The communications group needs some of their articles to be translated into various languages, by another group within the larger group. Both the creation of an article and its translation could be part of the same plan.

* An organization decides to mount a campaign for some objective.  There might be many different deliverables: a fundraising website, some brochures, some events, etc.  All of these can be part of the same plan for easier coordination.  For example, a campaign logo could be used in all of these separate outputs.

* An organization gets an order for some things they produce.  They can create a plan to produce to that order, including all line items.  Or they can gather all the orders for a time period for an item and produce to that as a larger plan.

* An organization produces a standard batch size to stock, in anticipation of future orders.

## Processes nested in a Plan

When processes are "nested", it is not random, nor based on a taxonomy. It is based on what processes are actually part of the plan. And not all the inputs and outputs of nested processes are considered inputs and outputs of the plan, since some are both produced and consumed within the plan.  In the following simplified example, the flows between plant/weed and weed/harvest start and end inside the nest, and so are not inputs to, or outputs of, the plan.

* There are some common situations for nested processes that will not be as simple as the above diagram.  These include:

    * Action makes a difference.  When a piece of equipment or tool is "used", it is not gone at the end of the nesting process.  But if it is managed as a time-based resource with a calendar, some calendar duration is in fact consumed.  Or if a citable resource is created and then cited inside, it is also still there at the end of the nesting process.
    * Batch or lot size makes a difference. Suppose you have a requirement for 5 of some assembled item, and 4 of some input component are needed to make each item, 20 components in all. But the minimum batch size for the component is 100. Then 80 of the components will be left in inventory at the end of the nesting process, and that 80 will also an output of the outer process.

## Planning from a Recipe

Plans can be generated from a recipe by scaling the recipe according to the demanded quantity of the end outputs.  This is called a "demand explosion".  The generation might take into account current inventories, batch sizes, etc., so it is not necessarily a "pure" reflection of the recipe.  In addition, often plans are tweaked after generation from a recipe, depending on how firm and exact the recipe is.  A manufacturing recipe might be more exact than a recipe for a more general business process.  For these reasons, a plans is decoupled from the recipe that generated it in the vocabulary.  It maintains only the references to the resource and process specifications that were supplied from the recipe.

Scenarios define high-level strategies. They contain Processes and Transfers.

See also Flows in motion: Estimation and Analysis on the Diagrams Explanation, and Estimate and Analysis examples.

## Scenarios

The Processes section explains processes at their basic level, starting with operational observable processes. The Transfers section explains non-process flows.  The Operational Planning section explains how to group those processes and transfers into a scheduled plan at an operational level. This section explains how to use the same process, transfer, and plan pattern to represent higher level requirements, those that are not (yet) actually scheduled, or already aggregated data.  We are calling that admittedly broad category Scenarios.

Processes and transfers can be composed into scenarios at any level.  Like scheduled plans, these scenarios can be created from recipes.  Like scheduled plans, they use the same input-output-process pattern and non-process-flow pattern. The flows in a scenario are usually intents, but sometimes sumarized economic events.

Some examples we have seen:

* Plan Refinement. Before the final operation plan is set, sometimes it is useful to make more general plans, which then can be refined further, ending with the scheduled plan.  These plans are estimates made using "planning horizons", which are defined durations starting from the planning date - for example year, then month, then blending into the actual scheduled plans.
* Budgeting.  A Budget is a summary of input requirements for a scope for a time interval (sometimes corresponding to the organization's "accounting period"), often yearly, as a higher level of planning. Budgets are often created to support a specific goal. Budgets are usually created before operational planning is done, and are estimates.  Often a forecast is made consisting of desired or expected deliverables for the period, sometimes using past event history as a starting point.  This would create a demand-driven budget.  Or sometimes a supply-driven budget makes more sense, for example when all of the producing capacity will be used in any case, and then the outputs will be constrained by the inputs available.  In any case, the budgeted inputs and outputs are kept, as they are often compared to actuals later.  The budget itself could be represented as a Process, and it could nest line item processes based on type of resource or process.  A budget is usually for one scope.
* Comparative Analysis.  Sometimes different plans will be created for the same basic data set.  One example is when doing risk analysis or other comparative analysis.  Different assumptions might skew a plan in different useful directions, for example a "normal scenario" and a "worst case scenario".
* Network Analysis.  This is an analytical look at all or some of the actual and/or potential resource flows for a scope, often a community or region.  This can be modeled using higher level types of processes and types of resources, and could include intents or economic events.  One use of this kind of analysis is to identify gaps and opportunities to keep resources circulating in a community to improve economic health and resilience.

Agents can define different scenarios that they want to use. So for example, if a group does yearly budgets, each budget for different years could reference the same "yearly budget" scenario definition.

The model itself is quite flexible, and we expect there will be more uses for it, all using the basic input-process-output structure with resource flows connecting them, contained by a scenario.

## Connecting Plans and Scenarios

Plans do not need to be directly connected to Scenarios, but sometimes they can be a refinement of a Scenario. If comparisons are needed, often the time periods and scope are all that is needed.  In addition, if resource specifications and/or process specifications are part of a classification taxonomy, that can be used for connecting the higher to lower perspectives.  For example, the plan for carrots could be aggregated into the higher level scenario for all vegetables.

Often Plans do not fit cleanly within Scenarios, because plans tend to be for real production when it happens, which usually does not fit nicely into accounting periods or planning horizons.  Seasonal food production can be an exception to this.

Scenarios can be refinements of other scenarios.  For example, a group might do scenarios for yearly estimates, then refine those for each month, before creating operational plans which will be executed.

If other requirements arise, we are happy to add connections as needed to the vocabulary.

See also Flows in Motion: Recipes on the Diagram Explanation, Planning from a Recipe on the Operational Planning page, and the Simple plan from recipe example.

## Not just for cooking...

Recipes are for:

* documenting how to do something,
* generating plans for people to do it together,
* providing signals for coordinating their work.

Recipes contain all the info required to create a resource or provide a service.  In ERP (Enterprise Resource Planning) terms, it’s a combination of bills of material and routings and suppliers. And the logic for generating plans from recipes is roughly the same as Material Requirements Planning.

If you encounter the same planning pattern more than once, and your software allows planning from recipes, you might want to capture the pattern in a Recipe so you don't need to cut and paste or re-enter the same information every time.

## Recipe patterns

These are two basic shapes of recipes. These recipe patterns can be used alone, or mixed and matched in the same recipe:

* Manufacturing pattern: assemble or transform input resources into different output resource(s). This combines bills of material, processing instructions (routings), other inputs like labor and equipment requirements, and possible suppliers for the inputs. The manufacturing pattern creates recursive structures. In other words, if an input component has a recipe itself, that recipe will be incorporated into its parent, so you can view a processing tree from parents through children unto many generations.  For example:

    * Assemble a robot from metal, wires, computer chips, software, etc.
    * Bake bread from flour, yeast, water, etc., using an oven.
    
A manufacturing recipe can be thought of like a tree shape, where the top of the tree produces the resource to be assembled, and the roots are all the components.
    
* Workflow pattern: change the same resource into a different stage of the same resource. This describes a sequence of processes used to complete work on one resource.  They create a series of stages that one resource will go through until it is finished. For example:

    * Translate a source document, edit the translation, format for publication, and publish.
    * Repair a bike.
    * Do quality testing on something that was created using the manufacturing pattern.
    
A workflow recipe tends to be more like a linear flow.

The examples above have to do with producing specific goods or services.  Recipes can also be used to document more general business processes that an organization uses to produce more generally defined kinds of outputs.  For example, an R&D process might be hard to document in detail, but it does have general steps like researching existing technology, concept generation, experimentation, concept selection, refinement, testing, documenting the design. 

## Recipe and Recipe Group

These are optional constructs.  You might want a Recipe when you include more than one process in one recipe, and especially if different recipes can create the same Resource Specification output in different ways.  It is also useful when certain processes are included in multiple recipes.

A Recipe Group is for when your plans regularly produce more than one output which can be produced separately.  For example, a campaign might produce one or more events, various brochures, a website, etc.

### Byproducts and Coproducts

A Recipe knows its primary output, i.e what is created by this Recipe.  As of now, it does not directly know its byproducts and coproducts, but this information can be added for specific use cases, outside of Valueflows, if needed. It can also be found by interrogating the contents of the recipe input-process-output graph. This choice favors simplicity at this stage.

## Generation of plans

Plans can be generated from a Recipe, a Recipe Group, or directly from a Recipe Process, which will find predescessor Recipe Processes as needed.

Back-scheduling a plan from a Recipe:
Start with end items and a due date, generate the plan from the end item to its inputs, to the outputs leading the inputs, to their inputs, etc.

Forward-scheduling from a Recipe:
Start with the inputs with no predecessors and a start date, generate the plan from the inputs to their outputs, to the inputs that want the outputs, etc.

Forward-scheduling from a Resource:
Start with a Resource and generate the plan based on its recipe.  Examples:

* Translation: start with a source document
* Auto repair: start with an auto that needs repair.

## Boundary for analysis and accounting

Scope can be thought of as a boundary for analysis and accounting, mostly used for sets of economic events, commitments, and intents.  A scope is an agent of some kind.  See also Agent concepts.

The scope is where work is done, where processes live, where value is created and exchanged. Economic events, commitments and intents can reference an organization, person, or ecological agent as an entity that defines their scope.

It is not required that events, commitments, or intents designate a scope.  In fact, sometimes the scope is the same as the provider or recipient agent.  Or sometimes there is no useful scope.

For functions that require traversing value flows, often the value flow will cross from one scope to another.  For example, perhaps another network or organization makes a component that you consume when making your product.  When this happens, there are some options.

* Standing agreements can govern what happens.
* A conversation for action might be required to determine what should occur for the specific instance.

## Accounting

Accounting is usually done for a bounded scope. Where a computer system supports one enterprise, this is simple.  When a computer system supports many organizations or there is a distributed network of economic activity, it is useful to be able to segregate the accounting using scope.  It basically enables multi-party accounting in a networked scenario.

## Planning

Sometimes a generic recipe will cross scope boundaries for particular agents. For example one agent could produce a resource that consumes a component made by another agent.  In this case, can the first agent schedule the production of the component by the second agent?  Possibly yes, if there are agreements in place for that, and the first agent has verified that inventory does not already exist.  Or possibly, based again on agreements, the first agent can assume the second agent will provide the component, with the second agent taking responsibility for checking if it is onhand, and if not, scheduling it for production.

## Distributing Incoming Resources

Some organizations distribute income backwards on value flows, based on people's contributions to the resources that generated the income.  When traversing the value chain, it is useful to know when the traversal has crossed a scope boundary, because it is possible that the rules for distributing the incoming resources will change for a different scope.  If the rules change or the rules are unknown, the income can be passed on to the other scope for them to distribute.

Note that income does not need to be money and can include distributing the output of a process to the contributors, like when a community farm distributes food to its contributors.

## Scoping Agents

Often the scope can be determined by already recorded agents, such as provider, receiver, subject, object.  But in other cases, for example when an organization is keeping track of activity or relationships between members, an explicit scoping agent is needed.  Implementations that use the scope concept may want to always record the scope of relevant entities, even when they can be implied.

# Accounting

## Recording Basic Economic Activity

The Valueflows vocabulary is based on the REA ontology (Resources, Events and Agents) the ISO Accounting and Economic Ontology, which was evolved for that purpose. (See Appendix for links.)

Since all the data is recorded as the economic activity happens and is represented in its most basic form, you can get separate accounting views for: a network, each group in the network, each project, each individual. In other words, people in the network log events as they occur and the accounting *Just Happens*.

All of the views can emerge from subsets of the same data.  Any standard (or non-standard) accounting report can be created.

Or potentially, views for a global value system economy (really).

See also Ecological Accounting.

## Accounting views: independent vs dependent

Conventional accounting always takes the view of an individual agent: often a company. REA, and Valueflows, take an independent view, sometimes called a “collaboration space” or economic network or supply chain view.  At the same time, derived from the independent view, REA and Valueflows support each agent's own accounting view.

For example, from one agent's viewpoint, the exchange may be a "purchase", from the other agent's viewpoint, it might be a "sale". From the neutral viewpoint, it is an exchange of resources, with usually at least two flows of resources, from different directions.

For the individual agent’s accounting systems, assuming an Exchange of goods for money, when the goods are transferred from the seller to the purchaser, the purchaser’s Accounts Payable are increased (credited) and the seller’s Accounts Receivable are increased (debited). The independent view sees a transfer of goods from one agent to another.

While conventional accounting uses the individual agent view, larger-scale economic analyses and planning, like for networks, communities, and bioregions, use the independent view. See Value Flow Algorithms.

## Accounting as in Accountability...

* from peers to each other
* from members to a network
* from a network to the members
* from one network to another
* from a network to the community
* from a network to the ecosystem

Accounting isn't always just counting beans.  It will be important for community economies: what resources do we have, what happened with them, how are they doing? What resources do we need? Who needs what? Who can provide what?  What waste have we generated and how can we improve?

## But if you want to count beans...

The standard set of accounting reports are needed by many organizations. A standard General Ledger, Balance Sheet, and Income Statement can be generated automatically from Valueflows data. No need to create a Chart of Accounts or post double-entries, those can all be created by a computer program on request.

Moreover, General Ledgers and accounting reports can be created automatically for each agent in an economic network using the VF vocabulary.  The accounting views use the Dependent or Individual Agent view of ValueFlows.

Accounting statements can also be updated instantly for each participant in any economic event as soon as the event is recorded. For example, consider an economic exchange, where one agent transfers some goods to another, and the other agent transfers some money in return. The inventory of the goods-providing agent will be instantly decremented, and the receiving agent's incremented. Likewise the money accounts of the money-providing and receiving agents will immediately change. Income statements, balance sheets, and cash flow reports can reflect the new changes immediately. The financial positions of each agent can always be up-to-date as of the last recorded event.

This article describes how to generate General Ledgers etc. from REA data using procedural code: Operation of a Relational Accounting System, Graham Gal and Bill McCarthy

Wim Laurier is working on how to do it declaratively. This paper gives an early view of how Wim and Satoshi Horiuchi intend to do it.

The difference between doing it procedurally and doing it declaratively:

* A procedural program defines a step-by-step method of getting the desired results.
* A declarative program describes the desired results and hands it to another program that can generate the desired results from your description. The person who desires the results writes much less code.

## Making Corrections

It is standard accounting practice that recorded activity that affect financial and other accounting reports cannot be changed directly in case of error.  That is because one cannot tell when reports could have been published containing that data, and many financial reports cannot be amended.

Valueflows allows for correction of an economic event with another economic event, which should be recorded with a `corrects` link to the original event.  This gives flexibility to display the event as corrected, or as separate events, depending on the need.  The quantity should be the amount to be added or subtracted from the original event quantity.  So this works differently than the increment/decrement rules, and will be the only time negative quantities can be used.  It is not required, but is often customary to completely "back out" or "reverse" the original record (i.e. if the quantity was 10, then the quantity of the correction record is -10, as of the date corrected); then the original event can be re-entered correctly with the earlier correct date and no need for the `corrects` link. Alternatively, the correction event could just record the difference, as of the date of correction, with the `corrects` link to the original.

If the original event was input to or output of a process, or was part of an agreement, then the correction event should contain those same relationships so it will appear embedded into the flow(s) where it belongs without worrying about the `corrects` link.  The correction event should be recorded as of the date of the correction, though.

All events should record the computer-generated `created` date/time also, as this may be used in periodic reports to keep the events filtered properly without missing or double counting anything; or where it is important to be able to compare traces (for example) to verify representation of the same resource based on history. (This is also needed when events are allowed to be recorded after the fact, irrespective of corrections, which is true for many situations.  That is, often the event date will be earlier than the created date.)

# Ecological Accounting

## Why ecological accounting

There is increasing desire to account for "externalities" from human production and transportation processes, and certainly the need has always been there. Related, there are also more efforts to do "climate accounting" on a global level, to provide knowledge in the efforts to improve the situation, which is spiraling out of control on many levels - climate chaos, soil and biodiversity loss, uncontrolled emission of substances on the land and in the water toxic to life, etc.

There are many reasons this has not been part of the accounting paradigm, including interests of corporate players and tendencies of industrial era humans to think about "the environment" as something separate from us, from which we can extract resources without regard to the many interconnections.  Although there are some efforts to give ecosystems rights relative to human impact, and helpful ways to think about the issues from indigenous sources and people working on the "commons", a large "paradigm shift" will be needed and there is much inertia and resistance.

As always, our goal is to give Valueflows the latitude to support both conventional and next economy accounting.  The latter will more and more involve ecological accounting.

So, understanding there will be much more learned going forward in practice, we want to make Valueflows broadly supportive of these efforts.  In general, this can be a step forward in being able to broaden our ability to do the accounting we need to do to confront the current climate and biodiversity challenges.

See also Accounting.

## REA I-P-O resource flows

The Valueflows input-process-output resource flow model works very well for ecological accounting, with some broadening of our thinking about agents and resources, and what "economic" entails.  If we think of "economic" as broader than human activity, which has tentacles into most if not all of the other ecosystems on earth, it becomes easier to consider "accounting" in light of flows to and from those ecosystems, all of which eventually affect human economies.

This diagram shows some of the flows for solar panel production.  Silica dust is an output of the mining process, which gives mine workers silicosis.  There are many additional flows here which could be detailed to go into and out of ecological ecosystems, affecting them and also humans.

## Economic Resources

We have thought of economic resources as having use value (and sometimes exchange value) to humans and ecosystems.  If we broaden that to include "bad" as well as "good" resources, we can model more completely and accurately the resource flows that impact ecosystems including humans.  It is also not very helpful to even think in terms of "bad" and "good", since that is conditional.  For example, CO2 is "good" for plants in a greenhouse, but "bad" pumped into the atmosphere, and some of the CO2 in the greenhouse will leak out, making it "bad"... yet it is the same substance.

## Agents

We have defined Agents as people and organizations (formal or informal).  If we go beyond human-centric thinking, we could conceive of Agents as other living things, and also as groups of other living things, or whole ecosystems.  Those ecosystems could be of any size or complexity, and all types of agents could have various relationships between each other and their ecosystems.

This requires some things which are traditionally considered by humans to be resources, to be considered agents in their own right.  We understand that some living things (say beef cattle being raised by a farmer) need to be accounted for as resources, and Valueflows will of course continue to support that.  On the other side of the puzzle, we also realize that we could consider a human being as an ecosystem, given the microbiota that lives there and even influences behavior.  So, the goal is to keep the model simple and flexible enough to support current practices, while also supporting continuing exploration and expansion of our thinking about agency within the global ecosystem of living beings.

But how can these non-human agents give input to human accounting systems?  One way is through sensors; another is through human "representatives".  Of course, this is all still unavoidably human-centric.  Some ecological agents need human agents to represent them in human governance activities, similar to specific humans representing organizations. This idea has both supporters and opposition: Federal Judge Strikes Down Lake Erie Bill of Rights. And there are evolving experiments to refine how humans cant on behalf of ecosystems, and to include indigenous groups who have had responsibility going back centuries. There are many ethical, legal, and practical considerations, but we think it is important to support wishes to account for climate change and harm from externalities.
