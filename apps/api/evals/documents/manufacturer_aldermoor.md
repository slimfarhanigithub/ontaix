# Aldermoor Valves Business Process Handbook

Aldermoor Valves is a fictional company, and this handbook was written as evaluation material for ontology extraction.

## Purpose Of This Handbook

This handbook describes how Aldermoor Valves turns customer demand into shipped valves and actuators, and how the money, materials and quality evidence move along the way. It is the reference for process owners, plant leaders, key users of the business systems and new joiners who need to understand where their work fits.

The handbook is written from the process point of view rather than the organisation chart. A team may take part in several processes, and a process may cross several teams. Where a process hands work to another process, the handbook says so explicitly, because most of our historic problems came from unclear hand-offs rather than from poor work inside a team.

Each process section names the owner, the main output and the documents or records that the steps produce. The owner is accountable for the design of the process, its performance measures and the changes made to it. Day-to-day execution sits with the teams that run the steps.

## Company Context

Aldermoor Valves designs and manufactures industrial gate, globe and ball valves, together with the electric and pneumatic actuators that operate them. Our customers are water utilities, chemical plants, power stations and the engineering contractors that build them. Most orders are engineered to a customer specification, although a growing share of the business is standard catalogue products and spare parts.

The company was founded as a small foundry workshop and grew into a discrete manufacturer with around 1,400 employees. Manufacturing runs in three sites. The Carrow site machines valve bodies and assembles large gate valves. The Leventon site builds actuators and control packages. The Brisk Hill site assembles small ball valves and runs the central distribution warehouse.

Demand follows the investment cycles of our customers. Large infrastructure projects bring engineered orders that take months to specify and deliver, while maintenance budgets drive a steadier flow of spare parts and catalogue valves. The aftermarket business is less exposed to project delays and has become an important source of stable margin.

The market expects short lead times, full traceability of pressure-retaining parts and certificates that prove every valve was tested. These expectations shape the design of every process in this handbook. A valve that leaves the plant without a traceable test record cannot be installed by the customer, so quality evidence is treated as part of the product, not as paperwork around it.

## Domains At A Glance

Aldermoor Valves runs Order-to-cash, Procure-to-pay, Plan-to-produce, Quality management and Master data management as its core domains. The first four domains carry the flow of orders, materials and evidence. Master data management supplies the shared records that all of them read.

The domains are connected through documents and records rather than through meetings. A sales order in one domain becomes a planned requirement in another, a purchase order in a third, and eventually a test certificate and an invoice. The sections below follow that flow.

## Order-to-cash

Order-to-cash covers everything from the first customer enquiry to the moment the payment is cleared in the ledger. Order-to-cash consists of quote-to-order, fulfilment and billing. The domain is sponsored by the commercial director, who chairs the monthly order-to-cash review.

### Quote-to-order

Quote-to-order turns a customer enquiry into a confirmed, credit-approved order. Quote-to-order is owned by the head of sales, and its main output is the sales order. Quote-to-order consists of quotation and order capture.

Quotation is the part of the work where the sales engineers understand what the customer needs and what it will cost. Quotation includes configuration check and price calculation. The configuration check confirms that the requested valve size, pressure class, materials and actuator can be built together. The configuration check produces a technical datasheet. The datasheet is shared with the customer so that their engineers can confirm the specification before any price is agreed.

Price calculation starts from the standard cost of the configured product and adds freight, testing and commercial terms. Price calculation produces the price quote. A price quote is valid for sixty days, after which the sales engineer must repeat the calculation with current material costs.

Order capture begins when the customer accepts the quote and sends a purchase instruction. Order capture consists of order entry and credit check. Order entry produces the sales order. Order entry reads the material master to confirm that every configured item exists and can be sold. The sales order carries the agreed delivery date, the price and any customer-specific testing requirements.

A rush order is a kind of sales order. Rush orders carry a premium and are allowed only when the plant confirms spare capacity. Spare parts orders from aftermarket customers are usually small, but those customers expect them to ship within two working days.

Every order above the customer credit limit waits for a financial decision. The credit check produces a credit decision. The credit check reads the customer master for the credit limit, the payment history and any open disputes. A negative credit decision blocks the sales order until the credit controller agrees a prepayment or a letter of credit.

### Fulfilment

Fulfilment moves finished goods from the plant to the customer site. Fulfilment is owned by the logistics manager, and its main output is the delivery note. Fulfilment includes picking and shipping.

Picking produces a pick list. The pick list tells the warehouse operator which finished valves, actuators and loose parts belong to the delivery, and in which order to collect them. Picking is performed in the Brisk Hill warehouse for catalogue products and at the producing site for engineered valves.

Shipping produces the delivery note. Shipping attaches the test certificate to every consignment, because customers will not accept a pressure-retaining product without it. The delivery note lists the serial numbers of every valve so that the customer can trace each unit back to its test record.

### Billing

Billing turns shipped goods into cash. Billing is owned by the credit controller, and its main output is the customer invoice. Billing consists of invoicing and collection.

Invoicing produces the customer invoice. The invoice is created automatically when the shipment is posted, and it repeats the price and payment terms agreed in the sales order. Engineered orders with milestone payments follow the same route, with one invoice per milestone.

Collection makes sure that invoices are paid on time. Collection consists of cash application and dunning. Cash application matches incoming bank payments against open invoices and clears them in the ledger. Payments that cannot be matched are parked on a suspense account and investigated within three working days. Dunning follows up invoices that are overdue. Dunning produces a dunning letter. The dunning letter escalates in three stages, from a friendly reminder to a formal notice that stops further deliveries.

## Procure-to-pay

Procure-to-pay covers the purchase of raw materials, bought-in components and services, from the choice of supplier to the payment of the supplier invoice. Procure-to-pay consists of sourcing, purchasing, receiving and supplier payment. The domain is sponsored by the procurement director.

### Sourcing

Sourcing decides which suppliers Aldermoor Valves will buy from and on what terms. Sourcing is owned by the procurement manager, and its main output is the supplier audit report. Sourcing has three spend categories: castings, electronics and seals. Castings cover valve bodies and bonnets from approved foundries. Electronics cover the motor drives and position sensors used in actuators. Seals cover gaskets, packings and O-rings in elastomer and graphite.

Sourcing consists of supplier selection. Supplier selection includes supplier qualification and request for quotation. Supplier qualification produces a supplier audit report. Supplier qualification updates the supplier master with the approval status and the scope of approved parts. A supplier without an approved status cannot receive a purchase order for pressure-retaining parts.

The request for quotation produces supplier bids. Buyers compare bids on price, lead time, quality history and the cost of transport to the receiving plant. The winning bid is recorded as the agreed price for the part and the supplier.

### Purchasing

Purchasing converts a material need into a commitment to a supplier. Purchasing is owned by the purchasing lead, and its main output is the purchase order. Purchasing consists of requisitioning and purchase order creation.

Requisitioning produces the purchase requisition. Most requisitions are created automatically by planning, while indirect materials and services are requested by hand. A requisition above the spending threshold needs approval by the budget holder.

Purchase order creation produces the purchase order. The purchase order states the part, the quantity, the agreed price, the delivery date and the receiving plant. A blanket purchase order is a kind of purchase order. Blanket purchase orders cover a year of castings or seals with call-offs released as planning needs them.

### Receiving

Receiving accepts delivered goods into stock. Receiving is owned by the warehouse manager, and its main output is the goods receipt note. Receiving consists of goods receipt and put-away.

Goods receipt produces the goods receipt note. The warehouse team counts the delivered quantity, checks the packaging and records the supplier batch numbers. Goods receipt triggers the incoming inspection for every part that the inspection plan marks as critical. Put-away moves released goods to their storage location once the inspection allows it.

### Supplier Payment

Supplier payment settles what Aldermoor Valves owes. Supplier payment is owned by the accounts payable lead, and its main output is the payment advice. Supplier payment consists of invoice verification and payment run.

Invoice verification includes the three-way match. The three-way match compares the supplier invoice with the purchase order and the goods receipt note. The three-way match produces a match exception whenever price or quantity differ beyond the tolerance. Exceptions are resolved by the buyer, not by accounts payable, because the buyer owns the supplier relationship.

The payment run produces a payment advice. The payment run executes twice a week and pays every verified invoice that is due. The payment advice tells the supplier which invoices each bank transfer settles.

## Plan-to-produce

Plan-to-produce turns demand into finished, tested products. Plan-to-produce consists of demand planning, production planning and production execution. The domain is sponsored by the operations director, who also chairs the weekly capacity meeting across the three sites.

### Demand Planning

Demand planning builds one agreed view of what customers will order. Demand planning is owned by the demand planner, and its main output is the demand forecast. Demand planning consists of sales forecasting and consensus planning.

Sales forecasting produces the demand forecast. The forecast covers eighteen months by product family and by month, and it combines order history with the sales pipeline. Consensus planning produces the consensus plan. The consensus plan is the single number that sales, operations and finance agree to work towards each month.

### Production Planning

Production planning decides what to make, where and when. Production planning is owned by the supply chain manager, and its main output is the production order. Production planning consists of master scheduling and material requirements planning.

Master scheduling produces the master production schedule. Master scheduling checks the work centre capacity at each plant before a date is committed to the customer. The master production schedule is frozen for two weeks, and changes inside that window need the approval of the plant manager.

Material requirements planning includes net requirements calculation and planned order conversion. Net requirements calculation produces planned orders. Net requirements calculation explodes the bill of materials to find every component that the schedule needs. Planned order conversion produces the production order. A rework order is a type of production order. Rework orders repair valves that failed a test and carry their own routing and cost collection.

### Production Execution

Production execution builds the product on the shop floor. Production execution is owned by the plant manager, and its main output is the test certificate. Production execution consists of shop floor control and final assembly.

Shop floor control includes order release and operation confirmation. Order release produces the job traveller. Order release uses the routing to print the sequence of operations on the traveller. Operation confirmation produces a confirmation record. Operators confirm quantities, scrap and time at the end of each operation, so that cost and progress are always current.

Final assembly includes valve assembly and pressure testing. Valve assembly fits the trim, the seals and the actuator to the machined body. Pressure testing produces the test certificate. Every valve is tested at one and a half times its rated pressure, and the test certificate records the test pressure, the duration and the inspector.

## Quality Management

Quality management makes sure that every valve meets its specification and that the evidence for it exists. Quality management consists of quality planning, quality control and nonconformance management. The domain is sponsored by the quality director, who reports directly to the managing director.

### Quality Planning

Quality planning decides what will be inspected and how. Quality planning is owned by the quality engineering lead, and its main output is the inspection plan. Quality planning includes inspection planning.

Inspection planning produces the inspection plan. The inspection plan lists inspection characteristics such as wall thickness, surface finish, seat leakage and coating depth. Each characteristic carries a tolerance and a sampling rule, so that inspectors apply the same standard at every site.

### Quality Control

Quality control applies the inspection plan to real parts and products. Quality control is owned by the quality manager, and its main output is the usage decision. Quality control has two inspection types: incoming inspection, in-process inspection and final inspection. Incoming inspection checks bought-in parts, in-process inspection checks machined bodies between operations, and final inspection checks the finished valve before packing.

Quality control includes sampling and results recording. Sampling draws the number of units that the inspection plan requires from each lot. Results recording produces the usage decision. The usage decision accepts, rejects or releases a lot under concession.

### Nonconformance Management

Nonconformance management deals with anything that does not meet its specification. Nonconformance management is owned by the quality manager, and its main output is the CAPA record. Nonconformance management consists of root cause analysis and corrective action.

A rejected usage decision triggers root cause analysis. Root cause analysis produces an 8D report. The report describes the problem, the containment, the root cause and the verification of the fix. Corrective action produces the CAPA record. The CAPA record stays open until the quality engineer has proved over three consecutive lots that the problem does not return.

## Master Data Management

Master data management keeps the shared records that every other domain reads. Master data management consists of product data management, production data management and partner data management. The domain is sponsored by the finance director, and a small central team of data stewards maintains the records for all three sites.

### Product Data Management

Product data management is owned by the master data lead, and its main output is the bill of materials. Product data management maintains the material master and the bill of materials. The material master holds the description, unit of measure, weight and valuation of every part and product.

The bill of materials has BOM items. Each BOM item names a component, the quantity per assembly and the plant that supplies it. An engineering BOM is a kind of bill of materials. The engineering BOM reflects the design as released by engineering, before the plant adds its manufacturing detail.

### Production Data Management

Production data management is owned by the master data lead, and its main output is the routing. Production data management maintains the routing and the work centre. The routing consists of routing operations. Each routing operation has a standard time that planning and costing use.

The work centre has a capacity profile. The capacity profile states the available hours per shift, the number of shifts and the planned maintenance windows. Examples of work centres are the horizontal boring mills at Carrow and the test benches at Brisk Hill.

### Partner Data Management

Partner data management is owned by the master data lead, and its main output is the customer master. Partner data management maintains the customer master and the supplier master. The customer master holds addresses, payment terms, credit limits and the certificates each customer requires. The supplier master holds bank details, approval status and the parts each supplier may deliver.

## Process Overview

The table below summarises the owner and main output of each process described in this handbook.

| Process | Domain | Owner | Main output |
| --- | --- | --- | --- |
| Quote-to-order | Order-to-cash | Head of sales | Sales order. |
| Fulfilment | Order-to-cash | Logistics manager | Delivery note. |
| Billing | Order-to-cash | Credit controller | Customer invoice. |
| Sourcing | Procure-to-pay | Procurement manager | Supplier audit report. |
| Purchasing | Procure-to-pay | Purchasing lead | Purchase order. |
| Receiving | Procure-to-pay | Warehouse manager | Goods receipt note. |
| Supplier payment | Procure-to-pay | Accounts payable lead | Payment advice. |
| Demand planning | Plan-to-produce | Demand planner | Demand forecast. |
| Production planning | Plan-to-produce | Supply chain manager | Production order. |
| Production execution | Plan-to-produce | Plant manager | Test certificate. |
| Quality planning | Quality management | Quality engineering lead | Inspection plan. |
| Quality control | Quality management | Quality manager | Usage decision. |
| Nonconformance management | Quality management | Quality manager | CAPA record. |
| Product data management | Master data management | Master data lead | Bill of materials. |
| Production data management | Master data management | Master data lead | Routing. |
| Partner data management | Master data management | Master data lead | Customer master. |

## Roles And Responsibilities

Process owners are accountable for the design and performance of their process. They approve changes to the process, sign off new reports and decide on exceptions that the process rules do not cover. A process owner who is also a line manager keeps the two responsibilities separate, so that the process serves every site and not only the owner's team.

Key users are experienced staff at each site who train colleagues, test system changes and collect improvement ideas. Every process has at least one key user per site where it runs. Key users meet the process owner once a month to review open issues.

Data stewards maintain master data on request from the business. They do not decide what a record should contain; that decision stays with the process owner who uses the record. Stewards check that requests are complete and consistent before they create or change a record.

Plant managers are accountable for safety, output and cost at their site, and they lead the daily shop floor meeting where the previous day's output, scrap and safety events are discussed. They take part in the processes of several domains, but they do not own the process design outside production execution.

## Systems

The ERP system holds orders, stock, master data and the financial ledger for all three plants. The manufacturing execution system runs on the shop floor and records operation confirmations, scrap and machine states. The supplier portal lets suppliers see purchase orders, confirm delivery dates and upload their invoices.

Test benches write their results directly to the manufacturing execution system, which passes them to the ERP system when the order is completed. This direct link removes manual typing of test pressures, which was the main source of certificate errors in the past.

## Performance Measures

The operating committee reviews a small set of measures every month. Each measure has a single owner and a target that is agreed at the start of the year.

- On-time delivery measures the share of order lines shipped on or before the confirmed date.
- Days sales outstanding measures how long customers take to pay their invoices.
- Schedule adherence measures the share of production orders completed in the planned week.
- First pass yield measures the share of valves that pass the pressure test at the first attempt.
- Supplier defect rate measures the share of received lots rejected at incoming inspection.

Measures are published by site and by product family. A measure that misses its target for two consecutive months triggers a review led by the owner of the process concerned.

## Change Control

No process in this handbook changes without a request to its owner. The owner assesses the effect on other processes, agrees the change with the owners concerned and updates this handbook before the change goes live. Key users are trained before the go-live date, and the change is reviewed three months later to confirm that it delivered the expected benefit.

The handbook itself is reviewed once a year by the process owners together. Sections that no longer match the way work is done are rewritten, and the version history is kept by the quality director's office.
