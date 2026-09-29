# Corvane Digital Services Operating Model Handbook

Corvane Digital Services is a fictional organisation, and this handbook was written as evaluation material.

## Introduction

This handbook describes how Corvane Digital Services works, from the first conversation with a prospective client to the last payment on the last invoice. It is written for everyone who joins the firm, whether they write code, run a support shift, price a bid or close the books at month end. It explains who does what, which records matter, and how work moves from one team to the next.

Corvane is an IT services and consulting firm of about 1,800 people. We work from delivery centres in Lyon, Rotterdam, Porto and Krakow, and we serve clients across Europe in banking, insurance, retail, energy and the public sector. Most of our clients stay with us for several years, and many of them buy more than one kind of work from us.

The handbook is maintained by the Operating Model Office. It is reviewed every quarter, and each domain lead signs off the chapter that covers their area. When practice changes, the handbook changes first, so that new joiners never learn a way of working that the firm has already abandoned.

We have tried to keep the language plain. Where a term has a precise meaning at Corvane, the handbook defines it the first time it is used and uses it the same way afterwards. Where two teams have historically used different words for the same thing, we have picked one word and we ask everyone to use it.

The handbook is not a contract and it does not replace the policies published by Legal, Human Resources or Information Security. When this handbook and a policy disagree, the policy wins, and the Operating Model Office corrects the handbook at the next review.

## Context

Corvane was founded in 2009 as a small software house in Lyon. It grew through steady hiring and through two acquisitions, a data consultancy in Rotterdam in 2016 and an application support business in Porto in 2019. Each acquisition brought good people and its own habits, and for several years the firm ran slightly different ways of selling, delivering and billing in each location.

In 2023 the executive committee decided to converge on a single operating model. The reasons were practical. Clients who bought from more than one part of the firm received different contract formats, different status reports and different invoices. Staff who moved between locations had to relearn basic tools. The finance team spent the first week of every month reconciling time data from three separate systems.

The market has changed as well. Clients increasingly expect a supplier to take responsibility for outcomes, not only to provide people. They want fixed prices where the scope is clear, firm service commitments where we run their systems, and honest advice about where artificial intelligence will and will not help them. At the same time, rates for routine development work are under pressure from much larger offshore competitors.

Our people are the reason clients come back. Around a third of our staff have been with the firm for more than eight years, and many of our senior engineers started as graduates in one of our delivery centres. We invest about six percent of payroll in training, and every consultant has a personal development plan agreed with their line manager at the start of each year.

We also value openness with clients. When a project is in trouble, we say so early and we bring a recovery plan with the bad news. When a client asks for something that we do not do well, we say that too and, where it helps, we introduce a partner who does it better.

Our answer is to be precise about what we sell, disciplined about how we sell and deliver it, and transparent about how we charge for it. This handbook is the written form of that answer, and it will keep evolving as we learn.

## Operating Model Overview

Corvane Digital Services organises its work into Services, Sales, Delivery, Support and Finance. The services we sell are the reason the rest of the model exists, and every other part of the model is judged by how well it helps us sell, deliver, support and charge for those services.

In short, Services describes what we offer to clients. Sales turns client interest into signed orders. Delivery carries out the work that has been sold, whether as a project with an end date or as a continuing service. Support keeps client systems running once they are live. Finance records the time we spend, bills our clients, recognises revenue and collects cash.

Each part of the model has a lead who sits on the operating committee. The lead owns the ways of working in their chapter, the records those ways of working create, and the measures used to judge them. Handoffs are described in the chapter of the team that receives the work, because the receiving team is best placed to say what it needs.

The operating committee meets every two weeks. It reviews the pipeline, delivery health, service performance and cash, and it takes the decisions that this handbook reserves for it. Its minutes are published on the intranet within two working days.

## Services

Corvane sells services. Services has three offerings: Apps, Data and AI. Each offering is led by an offering director who owns its catalogue entries, its pricing guidance and its library of client references.

An offering is not a department. Consultants belong to a delivery centre and to a skills community, and they work on engagements from any offering. The offering structure exists so that clients see a clear catalogue, and so that we can measure which kinds of work grow, which earn their margin, and which need investment.

### Apps

Apps comprises application development, application modernisation and application management. Apps is our largest offering by headcount and revenue, and it is the one most new clients meet first.

Application development offers custom software build for clients who need a system that no package provides. A custom software build usually runs between four and twelve months and is carried out by a cross-functional team of eight to fifteen people. We build web platforms, integration layers and back-office tools, mostly in Java, C# and TypeScript.

Application modernisation offers legacy migration for clients whose core systems have become expensive or risky to run. A legacy migration moves an ageing application to a supported platform, often in the cloud, while keeping its business behaviour stable. We favour incremental migration over a single switch-over, because it shows value earlier and lowers the risk of a failed cut-over weekend.

Application management offers application maintenance for systems that Corvane built or inherited. Application maintenance covers corrective fixes, small enhancements and technical upkeep such as library upgrades and security patches. It is usually sold as a continuing service with monthly charges rather than as a project.

### Data

Data comprises data engineering, analytics and data governance. The Data offering came to Corvane largely through the Rotterdam acquisition, and it remains strongest in financial services and energy.

Data engineering offers data platform build. A data platform build designs and implements the storage, pipelines and access controls that let a client collect data from its operational systems and use it safely. Most platforms we build today run on a public cloud and follow a layered design from raw to curated data.

Analytics offers dashboard development. Dashboard development turns business questions into reports and interactive views that managers use every week. We insist on agreeing the definition of every measure with the client before a dashboard is built, because most arguments about dashboards are really arguments about definitions.

Data governance offers master data management. Master data management gives a client one trusted version of its key reference records, such as customers, products and suppliers, together with the rules and ownership needed to keep that version clean over time.

### AI

AI comprises AI strategy, machine learning engineering and generative AI. AI is the youngest offering and the fastest growing, and it draws on specialists from the Data offering as well as on its own team.

AI strategy offers the AI readiness assessment. An AI readiness assessment is a six-week engagement that reviews a client's data, skills, controls and candidate use cases, and it ends with a prioritised roadmap. It is often the first contract we sign with a new client.

Machine learning engineering offers model development. Model development covers the design, training, evaluation and deployment of predictive models, together with the monitoring needed to know when a model has drifted and must be retrained.

Generative AI offers conversational assistant build. A conversational assistant build delivers an assistant that answers staff or customer questions from the client's own documents, with access controls, evaluation and a route to a human built in from the start.

### Catalogue Governance

Each offering director publishes a service sheet for every concrete service, describing its purpose, typical scope, staffing pattern and price range. Bid teams must start from a service sheet when they propose work. A service without a sheet cannot be sold until the offering director has approved one, which keeps the catalogue honest and prevents one-off promises that nobody can keep.

New services are added twice a year. An offering director proposes a new service with a business case, a pilot client if one exists, and a view of the skills needed. The operating committee decides whether to add it, and the finance team confirms the price range before the service sheet is published.

Services are also retired. When a service has not been sold for eighteen months, or when its margin has stayed below the firm's floor for a full year, the offering director either proposes changes or withdraws it from the catalogue.

## Sales

Sales runs lead-to-order, the end-to-end flow that takes a client need from first contact to a booked order. Sales is organised by client, not by offering, and each strategic account has an account director who coordinates every opportunity for that client, whatever it contains.

Lead-to-order consists of pipeline management, qualification, bid management and contracting. The account director is accountable for the whole flow on their accounts, while specialists take the lead at particular points, such as the bid manager during a bid and the contract manager during contracting.

### Pipeline Management

Pipeline management consists of lead capture and opportunity registration. The aim is simple: every piece of potential work should be visible to the people who need to plan for it, as early as possible and with an honest view of how likely it is.

Lead capture records every sign of client interest, whether it comes from an account director, a partner, a marketing event or an existing delivery team. Delivery teams are an important source of leads, because they often see the client's next problem before anyone else does. A lead that has a named client contact, a described need and a rough timeframe moves on.

Opportunity registration creates the opportunity in the CRM with its client, offering, estimated value, expected close date and sales owner. From that point the opportunity appears in the weekly pipeline call, where account directors walk through changes to value, probability and timing.

We expect the pipeline to hold about three times the revenue we need to win over the next two quarters. When coverage falls below that level for any offering, the offering director and the sales director agree actions, such as targeted campaigns or partner approaches, and report them to the operating committee.

### Qualification

Qualification consists of fit assessment and the go/no-go decision. Qualification is where we decide whether to spend bid effort, which is expensive and always in short supply.

Fit assessment checks whether the opportunity matches our catalogue, whether we have the skills and capacity to deliver it, whether the client's budget is realistic, and whether we can win against the likely competitors. The account director completes the fit assessment with an offering representative and a delivery lead.

The go/no-go decision produces a qualification record. The qualification record states the decision, the reasons for it, the named bid manager if the answer is go, and any conditions attached, such as a partner we must bring in or a scope item we will refuse to take on.

Opportunities above 500,000 euros need the go/no-go decision to be taken by a sales director, and opportunities above two million euros need it to be taken by the operating committee. A no-go is not a failure. We would rather decline early than submit a weak proposal that damages our reputation with the client.

### Bid Management

Bid management consists of solutioning, pricing and proposal review. The bid manager runs each bid as a small project with its own plan, calendar and team, and keeps the account director informed at every step.

Solutioning produces the solution design. The solution design describes what we will do, which team will do it, how long it will take and what we need from the client. Solutioning selects services from the offerings, so that every element of the proposed work maps to a published service sheet.

Pricing produces the price model. The price model includes the rate card, which sets the daily rate for each grade and delivery location. Pricing also estimates the effort, adds a contingency for identified risks and checks the result against the target margin for the offering.

Proposal review is the last check before a proposal leaves the firm. A reviewer who did not work on the bid reads the proposal as the client would, checks it against the client's requirements, and confirms that the price model and the solution design tell the same story.

Bids that pass proposal review are submitted by the bid manager. After submission, the bid manager keeps a log of client questions and our answers, because those answers often become part of the contract.

### Contracting

Contracting consists of statement of work drafting and order booking. Contracting starts when the client selects Corvane and ends when the order is live in our systems and Delivery can start.

Every engagement runs under a master services agreement with the client, which sets the general legal terms. Statement of work drafting produces the statement of work, the document that describes one piece of work under that agreement and that both parties sign.

The statement of work contains the scope, the deliverables and the acceptance criteria. The scope says what is in and what is out. The deliverables are the things the client will receive. The acceptance criteria say how the client will decide that each deliverable is complete, and they are written so that a neutral reader could apply them.

A fixed-price statement of work is a kind of statement of work. It commits Corvane to a total price for a defined scope, so it needs tight acceptance criteria and a clear process for handling changes to the scope.

A time-and-materials statement of work is a type of statement of work. It commits Corvane to provide named skills at agreed rates, and the client pays for the time actually spent, within a ceiling that cannot be exceeded without written approval.

Order booking records the signed statement of work in the ERP and opens the project code that time and costs will be booked against. Order booking triggers the resource request, so that staffing can start on the day the contract is signed.

## Delivery

Delivery consists of the project delivery method, resource management and managed services. Delivery is led by the delivery director, and every engagement has a named delivery lead who is accountable for its outcome.

### Project Delivery Method

The project delivery method consists of initiation, design, build, test and transition. We use the same method for every project, whatever its size or offering, and we scale the level of documentation rather than skipping parts of it.

Each part of the method ends with a gate review, where the delivery lead, the project manager and a quality reviewer confirm that the work is ready to move on. Gate reviews are short, and they focus on evidence rather than on slides.

Initiation includes project kick-off and project planning. Initiation should last no longer than three weeks, even for large programmes.

Project kick-off produces the project charter. Project kick-off reads the statement of work, so that the team starts from exactly what was sold rather than from memories of the bid. The project charter records the objectives, the governance, the team and the client contacts.

Project planning produces the project plan. The project plan includes the RAID log, which tracks risks, assumptions, issues and dependencies and which the project manager reviews every week with the client.

Design includes requirements analysis. Requirements analysis produces the requirements specification, which the client reviews and signs before build begins. On agile projects the requirements specification is a living backlog, but it is still reviewed and baselined at the gate.

Build runs in sprints. Each sprint lasts two weeks, and each sprint produces an increment of working software that the client can see and try. Our own testing happens inside every sprint, with automated checks running on every change.

Test includes user acceptance testing. User acceptance testing is carried out by the client's users against the acceptance criteria, with Corvane providing support, test data and defect fixing. User acceptance testing produces the acceptance certificate, signed by the client, which closes the test part of the method.

The acceptance certificate triggers the billing run for any milestone that depends on acceptance. Project managers must send the acceptance certificate to the finance team on the day it is signed.

Transition includes the go-live. The go-live triggers hypercare, a period of four to six weeks during which the project team stays close to the system and fixes problems quickly. Hypercare hands over to the service desk once the agreed exit conditions are met.

### Resource Management

Resource management consists of demand planning, staffing and bench management. It is run by the resource management team in each delivery centre, working to a single set of rules across the firm.

Demand planning looks twelve weeks ahead, combining booked work with weighted pipeline to forecast how many people of each skill we will need. The forecast is reviewed every Monday with the delivery leads and the offering directors.

Staffing consists of the resource request and the assignment. A resource request states the skill, grade, location, start date and expected duration of the role. The resource manager matches the request against the skills inventory and proposes candidates to the delivery lead.

The assignment confirms a named person on a project for a set period and a set allocation. An assignment is only confirmed when the person, their line manager and the delivery lead have agreed it, and it opens the project code for that person's time.

Bench management looks after consultants who are between assignments. Time on the bench is used for certification, internal tools and support to bids, and no consultant should spend more than four weeks there without a plan agreed with their line manager.

### Managed Services

Managed services runs service operation for clients who want Corvane to run their applications or data platforms over several years. Every managed services contract has a service level agreement that sets targets for availability, response and resolution.

Service operation includes service reporting. Service reporting produces the monthly service report, which shows performance against every target, the main incidents and changes of the month, and the improvements planned for the next period.

The service delivery manager presents the monthly service report to the client at the monthly service review. The service level agreement governs incident management, so the incident targets in each contract drive how the service desk prioritises its work for that client.

Quality in Delivery is everyone's job, but it is checked independently. A quality reviewer from outside the engagement looks at every project at least once a quarter, and more often when the project is large, late or new to us. The reviewer reports to the delivery director, not to the project, so that bad news travels quickly and without filtering.

## Support

Support consists of the service desk, incident management, problem management and change management. Support runs around the clock for clients with extended coverage and during business hours for everyone else.

### Service Desk

The service desk has three tiers: Tier 1, Tier 2 and Tier 3. Each tier has a clear boundary, and a ticket moves up only when the lower tier has done everything it is allowed and able to do.

Tier 1 performs triage. Triage confirms who the caller is, captures the symptoms, checks known errors and either resolves the request on the spot or passes it to the right team.

Tier 2 is staffed by application and platform specialists who can read logs, change configuration and apply documented fixes. Tier 2 resolves most tickets that Tier 1 cannot close.

Tier 3 is made up of the engineers who build and maintain the client's systems, usually from the application maintenance team. Tier 3 feeds problem management with every incident that needs a code change or that keeps coming back.

The service desk handles every ticket, whatever channel it arrives through. An incident is a type of ticket, raised when something that used to work has stopped working or is degraded. A service request is a kind of ticket, raised when a user asks for something standard, such as access, information or a new account.

### Incident Management

Incident management consists of incident logging, incident classification and incident resolution. The goal is to restore normal service as quickly as possible, not to find the underlying cause.

Incident logging records the incident in the ITSM platform with the caller, the affected service, the symptoms and the time it was reported. Nothing is worked on until it has been logged, because an unlogged incident cannot be measured against the service level agreement.

Incident classification uses the priority matrix. The priority matrix combines impact and urgency. The result is a priority from P1, the most severe, to P4, and the priority sets the response and resolution clocks.

Incident resolution restores the service, either with a permanent fix or with a workaround. When a P1 incident is open, the major incident manager runs a bridge call every hour and keeps the client informed until service is restored.

### Problem Management

Problem management consists of root cause analysis and known error recording. Problem management looks for the underlying causes of incidents so that they stop happening.

Root cause analysis produces the root cause report. The root cause report describes what happened, why it happened and what will be done to stop it from happening again, with named owners and dates.

Known error recording updates the known error database. The known error database holds every problem whose cause is understood, together with the workaround, and Tier 1 uses it to resolve repeat calls quickly.

### Change Management

Change management consists of change logging, change approval and change implementation. Change management protects live systems from avoidable disruption without slowing down routine work.

Change logging creates the change request. The change request describes what will change, why, when, the expected impact, the test evidence and the plan for backing out if something goes wrong.

A standard change is a kind of change request. Standard changes are low risk and follow a pre-approved procedure, so they skip the weekly board. An emergency change is a type of change request. Emergency changes fix a live problem that cannot wait, and they are reviewed after the event.

Change approval convenes the change advisory board. The change advisory board meets every Tuesday, and it includes the service delivery manager, the technical leads and a client representative.

Change implementation ends with a post-implementation review. The post-implementation review checks whether the change achieved its purpose and whether it caused any incidents, and it records any lessons for the next similar change.

## Finance

Finance consists of time capture, billing, revenue recognition and collections. The finance team works closely with project managers, because almost every number Finance reports starts with a record created in Delivery.

### Time Capture

Time capture consists of timesheet entry and timesheet approval. Accurate time data is the foundation of billing, revenue and staff utilisation, so time capture is treated as a core duty rather than as administration.

Timesheet entry produces the timesheet. Every consultant records their hours against project codes in the PSA tool by Friday afternoon each week, including internal time, bench time and leave.

Timesheet approval is done by the project manager for project time and by the line manager for internal time. Timesheets not approved by Monday noon are escalated to the delivery lead, because late approval delays the whole monthly cycle.

The timesheet feeds the billing run for time-and-materials work. The timesheet also feeds revenue recognition, since the hours spent on a fixed-price project measure its progress.

### Billing

Billing consists of the billing run and invoice dispatch. Billing runs on the third working day of every month for all clients, with additional runs for milestones reached during the month.

The billing run produces the draft invoice. The billing run reads the rate card, applies it to approved time, and adds any milestone amounts and expenses due. Each project manager reviews their draft invoice within one working day and confirms or corrects it.

Invoice dispatch sends the customer invoice. The customer invoice is issued from the ERP in the client's required format, often through an electronic invoicing portal, and it quotes the purchase order and the statement of work reference.

### Revenue Recognition

Revenue recognition applies the percentage-of-completion method to fixed-price work. The percentage-of-completion method compares the cost incurred to date with the total estimated cost, and it recognises the same share of the contract value as revenue.

Revenue recognition produces the revenue journal. The revenue journal is posted to the general ledger at month end, after the controller has reviewed every project whose estimate to complete has changed by more than ten percent.

For time-and-materials work, revenue follows approved time. For managed services, revenue is spread evenly over the service period, adjusted for any service credits owed under the contract.

### Collections

Collections has two dunning levels: reminder, formal notice and legal escalation. The credit controller sends a reminder seven days after the due date. A formal notice follows at thirty days, and legal escalation is considered at sixty days, always with the account director's agreement.

Collections produces the aged debt report. The customer invoice feeds the aged debt report, which groups open invoices by client and by age and is reviewed every week by the finance director and the sales director together.

Our target is to collect cash within forty-five days of invoicing on average. We achieve this mostly through accurate invoices, since a correct invoice sent on time is the one most likely to be paid on time.

## Roles

The following roles appear throughout the handbook, and each role has a written description on the intranet.

- Account director, who owns the relationship with a strategic client and every opportunity for that client.
- Offering director, who owns the catalogue, pricing guidance and references for one offering.
- Bid manager, who runs a bid from the go decision to submission.
- Contract manager, who negotiates terms and checks every statement of work before signature.
- Delivery lead, who is accountable for the outcome of an engagement.
- Project manager, who runs the day-to-day work of a project and approves project time.
- Resource manager, who matches people to requests in a delivery centre.
- Service delivery manager, who owns the relationship and the reporting for a managed service.
- Major incident manager, who coordinates the response to every P1 incident.
- Credit controller, who chases overdue invoices and agrees payment plans.

A person may hold more than one role on small engagements, but the account director and the delivery lead should always be different people, so that sales ambition and delivery realism are balanced.

## Systems

Corvane runs a deliberately small set of core systems, and every record described in this handbook has one system where it is mastered.

- The CRM holds leads, opportunities and qualification records.
- The PSA tool holds project codes, resource requests, assignments and timesheets.
- The ERP holds orders, invoices, the general ledger and receivables.
- The ITSM platform holds tickets, problems, known errors and change requests.
- The document store holds statements of work, project charters, plans and signed certificates.

Integrations between these systems run every night, and the order booking integration runs every hour. Data owners in each domain are accountable for the quality of the records mastered in their systems.

## Key Performance Indicators

The operating committee tracks a short list of measures, published every month on the performance dashboard.

- Pipeline coverage, the ratio of weighted pipeline to the revenue target for the next two quarters, with a target of three.
- Win rate, the share of submitted proposals that we win by value, with a target of forty percent.
- Utilisation, the share of available consultant time spent on billable work, with a target of seventy-eight percent.
- Project margin, the actual margin on closed projects compared with the margin in the price model.
- Service level attainment, the share of service level targets met across all managed services contracts.
- First-contact resolution, the share of tickets resolved by the first tier, with a target of sixty-five percent.
- Change success rate, the share of changes implemented without causing an incident.
- Days sales outstanding, the average number of days between invoice and payment, with a target of forty-five.

Each measure has one owner on the operating committee. When a measure misses its target for two months in a row, its owner presents a recovery plan at the next meeting.

## Keeping This Handbook Current

Anyone at Corvane can propose a change to this handbook by writing to the Operating Model Office. Proposals are grouped and reviewed every quarter with the relevant domain lead, and accepted changes are published with a short note explaining what changed and why.

The Operating Model Office also runs a short survey after each review, asking new joiners which parts of the handbook were unclear. Their answers are the best test of whether the handbook does its job.
