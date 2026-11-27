"""AL relationship facts. Source tables, fields, enums, relations, formulas, and action calls."""
from __future__ import annotations

from graphify.extract import _resolve_al_facts, extract_al


def _extract_all(paths):
    results = [extract_al(path) for path in paths]
    nodes = [node for result in results for node in result.get("nodes", [])]
    edges = _resolve_al_facts(results, nodes)
    return nodes, edges


def _write(dir_path, name, source):
    path = dir_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_source_table_bindings(tmp_path):
    page = _write(tmp_path, "Card.Page.al", """
page 50100 "Claim Card"
{
    SourceTable = "Claim Header";
    SourceTableView = where("No." = const(''));
}
""")
    table = _write(tmp_path, "Header.Table.al", """
table 50100 "Claim Header"
{
    fields
    {
        field(1; "No."; Code[20]) { }
    }
}
""")
    report = _write(tmp_path, "Claim.Report.al", """
report 50100 "Claim Report"
{
    dataset
    {
        dataitem(Header; "Claim Header")
        {
            dataitem(Line; "Claim Line") { }
        }
    }
}
""")
    query = _write(tmp_path, "Claim.Query.al", """
query 50100 "Claim Query"
{
    elements
    {
        dataitem(Cust; Customer)
        {
            column(Name; Name) { }
        }
    }
}
""")
    xmlport = _write(tmp_path, "Claim.Xmlport.al", """
xmlport 50100 "Claim Port"
{
    schema
    {
        tableelement(Cust; Customer)
        {
            fieldelement(No; Cust."No.") { }
        }
        textelement(Note) { }
    }
}
""")
    codeunit = _write(tmp_path, "Claim.Codeunit.al", """
codeunit 50100 "Claim Mgt"
{
    procedure Resolve()
    begin
        OnAfter();
    end;

    local procedure OnAfter()
    begin
    end;
}
""")

    nodes, edges = _extract_all([page, table, report, query, xmlport, codeunit])
    by_id = {node["id"]: node for node in nodes}

    def label(nid):
        return by_id[nid]["label"].strip('"')

    source_edges = [edge for edge in edges if edge["relation"] == "source_table"]
    pairs = {
        (label(edge["source"]), label(edge["target"]), edge["source_location"], edge["context"])
        for edge in source_edges
    }
    assert ("Claim Card", "Claim Header", "L4", "al_source_table") in pairs
    assert ("Claim Report", "Claim Header", "L6", "al_source_table:Header") in pairs
    assert ("Claim Report", "Claim Line", "L8", "al_source_table:Line") in pairs
    assert ("Claim Query", "Customer", "L6", "al_source_table:Cust") in pairs
    assert ("Claim Port", "Customer", "L6", "al_source_table:Cust") in pairs
    assert all(edge["confidence"] == "EXTRACTED" for edge in source_edges)
    assert not any("SourceTableView" in edge["context"] for edge in source_edges)

    external = [node for node in nodes if node.get("file_type") == "external"]
    assert {node["label"] for node in external} >= {"Claim Line", "Customer"}

    calls = [
        edge for edge in extract_al(codeunit)["edges"]
        if edge["relation"] == "calls"
    ]
    assert calls


def test_field_identity_and_enum_usage(tmp_path):
    header = _write(tmp_path, "Header.Table.al", """
table 50100 "Claim Header"
{
    fields
    {
        field(1; "No."; Code[20]) { }
        field(7; Status; Enum "Claim Status") { }
    }
}
""")
    other = _write(tmp_path, "Other.Table.al", """
table 50101 "Other Header"
{
    fields
    {
        field(1; "No."; Code[20]) { }
    }
}
""")
    enum = _write(tmp_path, "ClaimStatus.Enum.al", """
enum 50100 "Claim Status"
{
    value(0; Open) { }
}
""")
    extension = _write(tmp_path, "Header.TableExt.al", """
tableextension 50100 "Header Ext" extends "Claim Header"
{
    fields
    {
        field(50100; "Extra Status"; Enum "Claim Status") { }
    }
}
""")

    nodes, edges = _extract_all([header, other, enum, extension])
    by_id = {node["id"]: node for node in nodes}
    fields = [node for node in nodes if node.get("_origin") == "al_field"]

    def parent_label(node):
        return by_id[node["parent"]]["label"].strip('"')

    no_fields = [node for node in fields if node["label"] == "No."]
    assert len(no_fields) == 2
    assert {parent_label(node) for node in no_fields} == {"Claim Header", "Other Header"}
    assert len({node["id"] for node in no_fields}) == 2
    assert all(node["field_id"] == "1" for node in no_fields)
    assert all(node["data_type"] == "Code[20]" for node in no_fields)

    status = next(node for node in fields if node["label"] == "Status")
    assert parent_label(status) == "Claim Header"
    assert status["field_id"] == "7"
    assert status["source_location"] == "L7"

    extra = next(node for node in fields if node["label"] == "Extra Status")
    assert parent_label(extra) == "Header Ext"
    assert extra["parent"] != status["parent"]

    def edge_labels(relation):
        return {
            (by_id[edge["source"]]["label"].strip('"'), by_id[edge["target"]]["label"].strip('"'), edge["source_location"])
            for edge in edges if edge["relation"] == relation
        }

    assert ("Status", "Claim Status", "L7") in edge_labels("has_type")
    assert ("Extra Status", "Claim Status", "L6") in edge_labels("has_type")
    assert not any(edge["relation"] == "has_type" and by_id[edge["source"]]["label"] == "No." for edge in edges)
    assert ("Claim Header", "No.", "L6") in edge_labels("field")
    assert ("Header Ext", "Extra Status", "L6") in edge_labels("field")
    assert ("Header Ext", "Claim Header", "L2") in edge_labels("extends")
    opened = next(node for node in nodes if node.get("_origin") == "al_enum_value")
    assert opened["label"] == "Open"
    assert opened["value_id"] == "0"
    assert by_id[opened["parent"]]["label"].strip('"') == "Claim Status"


def test_table_relation_targets_and_branches(tmp_path):
    claim = _write(tmp_path, "Claim.Table.al", """
table 50101 "Warranty Claim"
{
    fields
    {
        field(2; "Warranty No."; Code[20])
        {
            TableRelation = Warranty."No.";
        }
        field(3; "Customer No."; Code[20])
        {
            TableRelation = Customer."No." where("Name" = field("Customer Name"));
        }
        field(4; Series; Code[20])
        {
            TableRelation = "No. Series";
        }
        field(5; Broken; Code[20])
        {
            TableRelation = ;
        }
        field(6; "Party No."; Code[20])
        {
            TableRelation = IF (Type = CONST(Customer)) Customer."No." ELSE IF (Type = CONST(Vendor)) Vendor."No." ELSE Contact."No.";
        }
        field(7; "Alt No."; Code[20])
        {
            TableRelation = IF (Type = CONST(A)) Warranty."No." ELSE Warranty."No.";
        }
    }
}
""")
    other = _write(tmp_path, "Other.Table.al", """
table 50102 "Other"
{
    fields
    {
        field(1; "No."; Code[20]) { }
    }
}
""")
    series = _write(tmp_path, "Series.Table.al", """
table 50103 "No. Series"
{
    fields
    {
        field(1; Code; Code[20]) { }
    }
}
""")
    extension = _write(tmp_path, "Claim.TableExt.al", """
tableextension 50100 "Claim Ext" extends "Warranty Claim"
{
    fields
    {
        field(50100; "Item No."; Code[20])
        {
            TableRelation = Item."No.";
        }
    }
}
""")
    warranty = _write(tmp_path, "Warranty.Table.al", """
table 50100 Warranty
{
    fields
    {
        field(1; "No."; Code[20]) { }
        field(2; Name; Text[50]) { }
    }
}
""")

    nodes, edges = _extract_all([claim, other, series, extension, warranty])
    by_id = {node["id"]: node for node in nodes}
    relations = [edge for edge in edges if edge["relation"] == "table_relation"]

    def node_of(label, parent_label):
        return next(
            node for node in nodes
            if node.get("label") == label
            and node.get("parent")
            and by_id[node["parent"]]["label"].strip('"') == parent_label
        )

    warranty_no = node_of("Warranty No.", "Warranty Claim")
    no_field = node_of("No.", "Warranty")
    other_no = node_of("No.", "Other")
    direct = next(edge for edge in relations if edge["source"] == warranty_no["id"])
    assert direct["target"] == no_field["id"]
    assert direct["target"] != other_no["id"]
    assert direct["source_location"] == "L8"
    assert direct["expression"] == 'Warranty."No."'
    assert direct["confidence"] == "EXTRACTED"
    assert "branch" not in direct

    customer = next(edge for edge in relations if edge["source"] == node_of("Customer No.", "Warranty Claim")["id"])
    assert by_id[customer["target"]]["label"] == 'Customer."No."'
    assert by_id[customer["target"]]["file_type"] == "external"
    assert customer["expression"] == 'Customer."No." where("Name" = field("Customer Name"))'
    assert customer["source_location"] == "L12"
    assert sum(edge["source"] == customer["source"] for edge in relations) == 1

    series_edge = next(edge for edge in relations if edge["source"] == node_of("Series", "Warranty Claim")["id"])
    series_table = next(node for node in nodes if node.get("label") == '"No. Series"' and node.get("field_id") is None)
    assert series_edge["target"] == series_table["id"]
    assert by_id[series_edge["target"]].get("field_id") is None

    assert not any(edge["source"] == node_of("Broken", "Warranty Claim")["id"] for edge in relations)

    party = node_of("Party No.", "Warranty Claim")
    party_edges = [edge for edge in relations if edge["source"] == party["id"]]
    assert {(edge["branch"], by_id[edge["target"]]["label"]) for edge in party_edges} == {
        ("Type = CONST(Customer)", 'Customer."No."'),
        ("else Type = CONST(Customer) | Type = CONST(Vendor)", 'Vendor."No."'),
        ("else Type = CONST(Customer) | else Type = CONST(Vendor)", 'Contact."No."'),
    }
    assert {edge["expression"] for edge in party_edges} == {
        'IF (Type = CONST(Customer)) Customer."No." ELSE IF (Type = CONST(Vendor)) Vendor."No." ELSE Contact."No."'
    }
    assert {edge["source_location"] for edge in party_edges} == {"L24"}

    alt = [edge for edge in relations if edge["source"] == node_of("Alt No.", "Warranty Claim")["id"]]
    assert len(alt) == 2
    assert {edge["target"] for edge in alt} == {no_field["id"]}
    assert {edge["branch"] for edge in alt} == {"Type = CONST(A)", "else Type = CONST(A)"}
    assert {edge["expression"] for edge in alt} == {'IF (Type = CONST(A)) Warranty."No." ELSE Warranty."No."'}

    item = next(edge for edge in relations if edge["source"] == node_of("Item No.", "Claim Ext")["id"])
    assert by_id[item["target"]]["label"] == 'Item."No."'
    assert by_id[item["source"]]["parent"] != warranty_no["parent"]
    assert any(
        edge["relation"] == "extends"
        and by_id[edge["source"]]["label"].strip('"') == "Claim Ext"
        and by_id[edge["target"]]["label"].strip('"') == "Warranty Claim"
        for edge in edges
    )


def test_calc_formula_targets_and_field_class(tmp_path):
    warranty = _write(tmp_path, "Warranty.Table.al", """
table 50100 Warranty
{
    fields
    {
        field(10; "Customer Name"; Text[100])
        {
            FieldClass = FlowField;
            CalcFormula = lookup(Customer.Name where("No." = field("Customer No.")));
        }
        field(11; "Claim Count"; Integer)
        {
            FieldClass = FlowField;
            CalcFormula = count("Warranty Claim" where("Warranty No." = field("No.")));
        }
        field(12; "Has Claim"; Boolean)
        {
            FieldClass = FlowField;
            CalcFormula = exist("Warranty Claim" where("Warranty No." = field("No.")));
        }
        field(13; "Total Amount"; Decimal)
        {
            FieldClass = FlowField;
            CalcFormula = sum("Warranty Claim".Amount where(Status = const(Open)));
        }
        field(14; "Avg Amount"; Decimal)
        {
            CalcFormula = average("Warranty Claim".Amount);
        }
        field(15; "Min Amount"; Decimal)
        {
            CalcFormula = min("Warranty Claim".Amount);
        }
        field(16; "Max Amount"; Decimal)
        {
            CalcFormula = max("Warranty Claim".Amount);
        }
        field(17; Broken; Integer)
        {
            CalcFormula = ;
        }
        field(18; Note; Text[50]) { }
    }
}
""")
    other = _write(tmp_path, "Other.Table.al", """
table 50102 Other
{
    fields
    {
        field(1; Name; Text[50]) { }
    }
}
""")
    extension = _write(tmp_path, "Warranty.TableExt.al", """
tableextension 50100 "Warranty Ext" extends Warranty
{
    fields
    {
        field(50100; "Open Count"; Integer)
        {
            FieldClass = FlowField;
            CalcFormula = count("Warranty Claim");
        }
    }
}
""")
    claim = _write(tmp_path, "Claim.Table.al", """
table 50101 "Warranty Claim"
{
    fields
    {
        field(1; "No."; Code[20]) { }
        field(2; Amount; Decimal) { }
        field(3; Name; Text[50]) { }
    }
}
""")

    nodes, edges = _extract_all([warranty, other, extension, claim])
    by_id = {node["id"]: node for node in nodes}
    formulas = [edge for edge in edges if edge["relation"] == "calc_formula"]

    def node_of(label, parent_label):
        return next(
            node for node in nodes
            if node.get("label") == label
            and node.get("parent")
            and by_id[node["parent"]]["label"].strip('"') == parent_label
        )

    claim_table = next(
        node for node in nodes
        if node.get("label") == '"Warranty Claim"' and node.get("field_id") is None
    )
    amount = node_of("Amount", "Warranty Claim")
    other_name = node_of("Name", "Other")

    customer = next(edge for edge in formulas if edge["source"] == node_of("Customer Name", "Warranty")["id"])
    assert customer["formula"] == "lookup"
    assert customer["expression"] == 'lookup(Customer.Name where("No." = field("Customer No.")))'
    assert customer["context"] == 'al_calc_formula:where("No." = field("Customer No."))'
    assert customer["source_location"] == "L9"
    assert customer["confidence"] == "EXTRACTED"
    assert by_id[customer["target"]]["label"] == "Customer.Name"
    assert by_id[customer["target"]]["file_type"] == "external"
    assert customer["target"] != other_name["id"]
    assert by_id[customer["source"]]["field_class"] == "FlowField"

    count = next(edge for edge in formulas if edge["source"] == node_of("Claim Count", "Warranty")["id"])
    exist = next(edge for edge in formulas if edge["source"] == node_of("Has Claim", "Warranty")["id"])
    assert count["formula"] == "count"
    assert exist["formula"] == "exist"
    assert count["target"] == exist["target"] == claim_table["id"]
    assert by_id[count["target"]].get("field_id") is None
    assert "where(" in count["context"] and "where(" in exist["context"]

    for label, function, location in (
        ("Total Amount", "sum", "L24"),
        ("Avg Amount", "average", "L28"),
        ("Min Amount", "min", "L32"),
        ("Max Amount", "max", "L36"),
    ):
        edge = next(edge for edge in formulas if edge["source"] == node_of(label, "Warranty")["id"])
        assert edge["formula"] == function
        assert edge["target"] == amount["id"]
        assert edge["source_location"] == location
    assert formulas[formulas.index(next(edge for edge in formulas if edge["formula"] == "sum"))]["context"].startswith("al_calc_formula:where(")
    assert next(edge["context"] for edge in formulas if edge["formula"] == "average") == "al_calc_formula"

    assert not any(edge["source"] == node_of("Broken", "Warranty")["id"] for edge in formulas)
    note = node_of("Note", "Warranty")
    assert "field_class" not in note
    assert not any(edge["source"] == note["id"] for edge in formulas)

    opened = next(edge for edge in formulas if edge["source"] == node_of("Open Count", "Warranty Ext")["id"])
    assert opened["formula"] == "count"
    assert opened["target"] == claim_table["id"]
    assert opened["context"] == "al_calc_formula"
    assert by_id[opened["source"]]["field_class"] == "FlowField"
    assert by_id[opened["source"]]["parent"] != node_of("Customer Name", "Warranty")["parent"]
    assert any(
        edge["relation"] == "extends"
        and by_id[edge["source"]]["label"].strip('"') == "Warranty Ext"
        and by_id[edge["target"]]["label"].strip('"') == "Warranty"
        for edge in edges
    )


def test_page_action_calls(tmp_path):
    card = _write(tmp_path, "Card.Page.al", """
page 50103 "Claim Card"
{
    actions
    {
        area(Processing)
        {
            action(StartProcessing)
            {
                trigger OnAction()
                var
                    ClaimMgt: Codeunit "Claim Mgt";
                begin
                    CurrPage.SaveRecord();
                    ClaimMgt.StartClaim(Rec);
                end;
            }
            action(Resolve)
            {
                trigger OnAction()
                var
                    ClaimMgt: Codeunit "Claim Mgt";
                    ClaimRec: Record "Claim Header";
                begin
                    CurrPage.SaveRecord();
                    ClaimMgt.ResolveClaim(Rec);
                    ClaimRec.Init();
                end;
            }
            action(Refresh)
            {
                trigger OnAction()
                var
                    ClaimMgt: Codeunit "Claim Mgt";
                begin
                    ClaimMgt.Run();
                end;
            }
            actionref(Resolve_Promoted; Resolve) { }
        }
    }
}
""")
    other = _write(tmp_path, "Other.Page.al", """
page 50104 "Other Card"
{
    actions
    {
        area(Processing)
        {
            action(Resolve)
            {
                trigger OnAction()
                var
                    OtherMgt: Codeunit "Other Mgt";
                begin
                    OtherMgt.ResolveClaim(Rec);
                end;
            }
        }
    }
}
""")
    extension = _write(tmp_path, "Card.PageExt.al", """
pageextension 50100 "Card Ext" extends "Claim Card"
{
    actions
    {
        addlast(Processing)
        {
            action(Reopen)
            {
                trigger OnAction()
                var
                    ClaimMgt: Codeunit "Claim Mgt";
                begin
                    ClaimMgt.ReopenClaim(Rec);
                end;
            }
        }
    }
}
""")
    management = _write(tmp_path, "Claim.Codeunit.al", """
codeunit 50100 "Claim Mgt"
{
    procedure StartClaim()
    begin
    end;

    procedure ResolveClaim()
    begin
        OnAfterClaimResolved();
    end;

    procedure ReopenClaim()
    begin
    end;

    trigger OnRun()
    begin
    end;

    local procedure OnAfterClaimResolved()
    begin
    end;
}
""")
    other_mgt = _write(tmp_path, "Other.Codeunit.al", """
codeunit 50101 "Other Mgt"
{
    procedure ResolveClaim()
    begin
    end;
}
""")

    nodes, edges = _extract_all([card, other, extension, management, other_mgt])
    by_id = {node["id"]: node for node in nodes}

    def trigger(label, parent_label):
        return next(
            node for node in nodes
            if node.get("label") == label
            and node.get("parent")
            and by_id[node["parent"]]["label"].strip('"') == parent_label
        )

    start = trigger("StartProcessing.OnAction", "Claim Card")
    resolve = trigger("Resolve.OnAction", "Claim Card")
    other_resolve = trigger("Resolve.OnAction", "Other Card")
    reopen = trigger("Reopen.OnAction", "Card Ext")
    assert len({start["id"], resolve["id"], other_resolve["id"], reopen["id"]}) == 4
    assert start["source_location"] == "L10"
    assert resolve["source_location"] == "L20"
    assert by_id[reopen["parent"]]["label"].strip('"') == "Card Ext"

    calls = [edge for edge in edges if edge["relation"] == "calls"]

    def call_from(source_id):
        return [edge for edge in calls if edge["source"] == source_id]

    start_calls = call_from(start["id"])
    assert [(by_id[edge["target"]]["label"], edge["source_location"], edge["confidence"]) for edge in start_calls] == [
        (".StartClaim()", "L15", "EXTRACTED")
    ]
    resolve_calls = call_from(resolve["id"])
    assert [(by_id[edge["target"]]["label"], edge["source_location"]) for edge in resolve_calls] == [
        (".ResolveClaim()", "L26")
    ]
    other_calls = call_from(other_resolve["id"])
    assert [by_id[edge["target"]]["label"] for edge in other_calls] == [".ResolveClaim()"]
    assert other_calls[0]["target"] != resolve_calls[0]["target"]
    assert [by_id[edge["target"]]["label"] for edge in call_from(reopen["id"])] == [".ReopenClaim()"]
    assert call_from(trigger("Refresh.OnAction", "Claim Card")["id"]) == []
    assert not any("SaveRecord" in edge.get("expression", "") or edge.get("expression", "").endswith(".Init") or edge.get("expression", "").endswith(".Run") for edge in calls)
    assert not any(node.get("label", "").startswith("Resolve_Promoted") for node in nodes)
    assert any(
        edge["relation"] == "extends"
        and by_id[edge["source"]]["label"].strip('"') == "Card Ext"
        and by_id[edge["target"]]["label"].strip('"') == "Claim Card"
        for edge in edges
    )
    codeunit_calls = [
        edge for edge in extract_al(management)["edges"]
        if edge["relation"] == "calls"
    ]
    assert codeunit_calls


def test_field_triggers(tmp_path):
    warranty = _write(tmp_path, "Warranty.Table.al", """
table 50100 Warranty
{
    fields
    {
        field(6; "Start Date"; Date)
        {
            trigger OnValidate()
            var
                WarrantyManagement: Codeunit "Warranty Management";
                Claim: Record "Warranty Claim";
            begin
                CheckStartAndEndDate();
                WarrantyManagement.SetWarrantyStatusFromDates(Rec);
                Claim.SetRange("No.", "No.");
            end;
        }
        field(7; "End Date"; Date)
        {
            trigger OnValidate()
            var
                WarrantyManagement: Codeunit "Warranty Management";
            begin
                CheckStartAndEndDate();
                WarrantyManagement.Run();
            end;
        }
        field(1; "No."; Code[20])
        {
            trigger OnValidate()
            begin
                TestField("No.");
            end;
        }
    }

    procedure CheckStartAndEndDate()
    begin
    end;
}
""")
    other = _write(tmp_path, "Other.Table.al", """
table 50101 Other
{
    fields
    {
        field(1; "No."; Code[20])
        {
            trigger OnValidate()
            begin
                CheckOther();
            end;
        }
    }

    procedure CheckOther()
    begin
    end;
}
""")
    extension = _write(tmp_path, "Warranty.TableExt.al", """
tableextension 50100 "Warranty Ext" extends Warranty
{
    fields
    {
        field(50100; "Extra Date"; Date)
        {
            trigger OnValidate()
            begin
                CheckStartAndEndDate();
            end;
        }
    }
}
""")
    management = _write(tmp_path, "Warranty.Codeunit.al", """
codeunit 50100 "Warranty Management"
{
    procedure SetWarrantyStatusFromDates()
    begin
    end;

    trigger OnRun()
    begin
    end;
}
""")

    nodes, edges = _extract_all([warranty, other, extension, management])
    by_id = {node["id"]: node for node in nodes}

    def field_trigger(label):
        return next(node for node in nodes if node.get("label") == label and node.get("_origin") == "al_field_trigger")

    start = field_trigger("Start Date.OnValidate")
    end = field_trigger("End Date.OnValidate")
    number = field_trigger("No..OnValidate")
    other_number = next(
        node for node in nodes
        if node.get("label") == "No..OnValidate"
        and node.get("id") != number["id"]
    )
    extra = field_trigger("Extra Date.OnValidate")
    assert len({start["id"], end["id"], number["id"], other_number["id"], extra["id"]}) == 5
    assert by_id[start["parent"]]["label"] == "Start Date"
    assert by_id[by_id[start["parent"]]["parent"]]["label"].strip('"') == "Warranty"
    assert by_id[by_id[extra["parent"]]["parent"]]["label"].strip('"') == "Warranty Ext"
    assert start["source_location"] == "L8"
    assert end["source_location"] == "L20"

    calls = [edge for edge in edges if edge["relation"] == "calls"]

    def targets(source_id):
        return sorted(
            (by_id[edge["target"]]["label"], edge["source_location"], edge["confidence"])
            for edge in calls if edge["source"] == source_id
        )

    assert targets(start["id"]) == [
        (".CheckStartAndEndDate()", "L13", "EXTRACTED"),
        (".SetWarrantyStatusFromDates()", "L14", "EXTRACTED"),
    ]
    assert targets(end["id"]) == [(".CheckStartAndEndDate()", "L24", "EXTRACTED")]
    assert targets(number["id"]) == []
    assert targets(extra["id"]) == []
    assert targets(other_number["id"]) == [(".CheckOther()", "L10", "EXTRACTED")]
    assert not any("SetRange" in edge.get("expression", "") or edge.get("expression", "").endswith(".Run") or edge.get("expression") == "TestField" for edge in calls)
    assert any(
        edge["relation"] == "extends"
        and by_id[edge["source"]]["label"].strip('"') == "Warranty Ext"
        and by_id[edge["target"]]["label"].strip('"') == "Warranty"
        for edge in edges
    )


def test_report_triggers(tmp_path):
    report = _write(tmp_path, "Claim.Report.al", """
report 50105 "Claim Report"
{
    dataset
    {
        dataitem(Header; "Claim Header")
        {
            dataitem(Line; "Claim Line")
            {
                trigger OnAfterGetRecord()
                var
                    LineRec: Record "Claim Line";
                begin
                    PrepareLine();
                    LineRec.Get("No.");
                end;
            }
            trigger OnAfterGetRecord()
            var
                Mgt: Codeunit "Claim Mgt";
            begin
                PrepareHeader();
                Mgt.Finish();
                Mgt.Run();
            end;
        }
    }

    trigger OnPreReport()
    var
        Mgt: Codeunit "Claim Mgt";
    begin
        PrepareReport();
        Mgt.Start();
    end;

    procedure PrepareHeader()
    begin
    end;

    procedure PrepareLine()
    begin
    end;

    procedure PrepareReport()
    begin
    end;
}
""")
    other = _write(tmp_path, "Other.Report.al", """
report 50106 "Other Report"
{
    dataset
    {
        dataitem(Header; "Claim Header")
        {
            trigger OnAfterGetRecord()
            begin
                PrepareOther();
            end;
        }
    }

    procedure PrepareOther()
    begin
    end;
}
""")
    management = _write(tmp_path, "Claim.Codeunit.al", """
codeunit 50100 "Claim Mgt"
{
    procedure Finish()
    begin
    end;

    procedure Start()
    begin
    end;

    trigger OnRun()
    begin
    end;
}
""")

    nodes, edges = _extract_all([report, other, management])
    by_id = {node["id"]: node for node in nodes}
    triggers = [node for node in nodes if node.get("_origin") == "al_report_trigger"]

    def one(label, parent_label):
        return next(
            node for node in triggers
            if node["label"] == label
            and by_id[node["parent"]]["label"].strip('"') == parent_label
        )

    header = one("Header.OnAfterGetRecord", "Claim Report")
    line = one("Line.OnAfterGetRecord", "Claim Report")
    prepare = one("OnPreReport", "Claim Report")
    other_header = one("Header.OnAfterGetRecord", "Other Report")
    assert len({header["id"], line["id"], prepare["id"], other_header["id"]}) == 4
    assert header["dataitem"] == "Header"
    assert line["dataitem"] == "Line"
    assert prepare["dataitem"] == ""
    assert header["source_location"] == "L18"
    assert line["source_location"] == "L10"
    assert prepare["source_location"] == "L29"

    calls = [edge for edge in edges if edge["relation"] == "calls"]

    def targets(source_id):
        return sorted(
            (by_id[edge["target"]]["label"], edge["source_location"], edge["confidence"])
            for edge in calls if edge["source"] == source_id
        )

    assert targets(line["id"]) == [(".PrepareLine()", "L14", "EXTRACTED")]
    assert targets(header["id"]) == [
        (".Finish()", "L23", "EXTRACTED"),
        (".PrepareHeader()", "L22", "EXTRACTED"),
    ]
    assert targets(prepare["id"]) == [
        (".PrepareReport()", "L33", "EXTRACTED"),
        (".Start()", "L34", "EXTRACTED"),
    ]
    assert targets(other_header["id"]) == [(".PrepareOther()", "L10", "EXTRACTED")]
    assert not any(
        "Get" in edge.get("expression", "") or edge.get("expression", "").endswith(".Run")
        for edge in calls
    )


def test_nested_triggers_do_not_keep_bare_nodes(tmp_path):
    page = _write(tmp_path, "Card.Page.al", """
page 1 Card
{
    actions
    {
        action(Resolve)
        {
            trigger OnAction()
            begin
            end;
        }
    }

    trigger OnAfterGetRecord()
    begin
        Refresh();
    end;

    procedure Refresh()
    begin
    end;
}
""")
    table = _write(tmp_path, "Item.Table.al", """
table 1 Item
{
    fields
    {
        field(1; "No."; Code[20])
        {
            trigger OnValidate()
            begin
                CheckNo();
            end;
        }
    }

    trigger OnInsert()
    begin
    end;

    procedure CheckNo()
    begin
    end;
}
""")
    report = _write(tmp_path, "Item.Report.al", """
report 1 "Item Report"
{
    dataset
    {
        dataitem(Header; Item)
        {
            trigger OnAfterGetRecord()
            begin
            end;
        }
    }

    trigger OnPreReport()
    begin
    end;
}
""")
    codeunit = _write(tmp_path, "Item.Codeunit.al", """
codeunit 1 Install
{
    trigger OnRun()
    begin
    end;
}
""")

    nodes, _edges = _extract_all([page, table, report, codeunit])
    labels = {node["label"] for node in nodes}
    assert "Resolve.OnAction" in labels
    assert "No..OnValidate" in labels
    assert "Header.OnAfterGetRecord" in labels
    assert ".OnAfterGetRecord()" in labels
    assert ".OnInsert()" in labels
    assert ".OnRun()" in labels
    assert "OnPreReport" in labels or ".OnPreReport()" in labels
    assert "OnAction()" not in labels
    assert "OnValidate()" not in labels
    assert "OnAfterGetRecord()" not in labels
    page_nodes = {node["id"]: node for node in extract_al(page)["nodes"]}
    assert any(
        edge["relation"] == "calls"
        and page_nodes[edge["source"]]["label"] == ".OnAfterGetRecord()"
        and page_nodes[edge["target"]]["label"] == ".Refresh()"
        for edge in extract_al(page)["edges"]
    )


def test_procedure_checks_are_not_calls(tmp_path):
    codeunit = _write(tmp_path, "Management.Codeunit.al", """
codeunit 1 Management
{
    procedure ResolveClaim()
    begin
        if Status <> 'In Progress' then
            Error(OnlyInProgressErr);
        TestField("Problem Description");
        Rec.FieldError(Status, 'bad');
        Validate(Status, 'Resolved');
        Modify(true);
        OnAfterClaimResolved();
    end;

    procedure OnAfterClaimResolved()
    begin
    end;

    procedure Other()
    begin
        if Status = 'New' then
            Error(OnlyNewErr);
    end;
}
""")
    other = _write(tmp_path, "Other.Codeunit.al", """
codeunit 2 Other
{
    procedure ResolveClaim()
    begin
        if Status = 'Other' then
            Error(OtherErr);
    end;
}
""")
    page = _write(tmp_path, "Card.Page.al", """
page 1 Card
{
    actions
    {
        action(Resolve)
        {
            trigger OnAction()
            begin
                if Ready then
                    Error(BlockedErr);
            end;
        }
    }
}
""")
    table = _write(tmp_path, "Item.Table.al", """
table 1 Item
{
    fields
    {
        field(1; "No."; Code[20])
        {
            trigger OnValidate()
            begin
                TestField("No.");
            end;
        }
    }

    trigger OnInsert()
    begin
        Error('missing');
    end;
}
""")
    report = _write(tmp_path, "Item.Report.al", """
report 1 "Item Report"
{
    dataset
    {
        dataitem(Header; Item)
        {
            trigger OnAfterGetRecord()
            begin
                Error(FailedErr);
            end;
        }
    }
}
""")

    nodes, edges = _extract_all([codeunit, other, page, table, report])

    def owner(label, filename):
        return next(
            node for node in nodes
            if node["label"] == label and filename in node.get("source_file", "").replace("\\", "/")
        )

    def checks_from(node):
        return sorted(
            (edge["check"], edge["expression"], edge["source_location"])
            for edge in edges
            if edge["relation"] == "checks" and edge["source"] == node["id"]
        )

    resolve = owner(".ResolveClaim()", "Management.Codeunit.al")
    assert checks_from(resolve) == [
        ("error", "Error(OnlyInProgressErr)", "L7"),
        ("fielderror", "Rec.FieldError(Status, 'bad')", "L9"),
        ("if", "Status <> 'In Progress'", "L6"),
        ("testfield", 'TestField("Problem Description")', "L8"),
    ]
    assert checks_from(owner(".Other()", "Management.Codeunit.al")) == [
        ("error", "Error(OnlyNewErr)", "L22"),
        ("if", "Status = 'New'", "L21"),
    ]
    assert checks_from(owner(".ResolveClaim()", "Other.Codeunit.al")) == [
        ("error", "Error(OtherErr)", "L7"),
        ("if", "Status = 'Other'", "L6"),
    ]
    assert checks_from(owner("Resolve.OnAction", "Card.Page.al")) == [
        ("error", "Error(BlockedErr)", "L11"),
        ("if", "Ready", "L10"),
    ]
    assert checks_from(owner("No..OnValidate", "Item.Table.al")) == [
        ("testfield", 'TestField("No.")', "L10"),
    ]
    assert checks_from(owner(".OnInsert()", "Item.Table.al")) == [
        ("error", "Error('missing')", "L17"),
    ]
    assert checks_from(owner("Header.OnAfterGetRecord", "Item.Report.al")) == [
        ("error", "Error(FailedErr)", "L10"),
    ]
    codeunit_nodes = {node["id"]: node for node in extract_al(codeunit)["nodes"]}
    calls = [edge for edge in extract_al(codeunit)["edges"] if edge["relation"] == "calls"]
    assert any(
        codeunit_nodes[edge["source"]]["label"] == ".ResolveClaim()"
        and codeunit_nodes[edge["target"]]["label"] == ".OnAfterClaimResolved()"
        for edge in calls
    )
    assert not any(
        edge.get("check") in {"error", "testfield", "fielderror"}
        or "Validate" in edge.get("expression", "")
        or "Modify" in edge.get("expression", "")
        for edge in calls
    )


def test_resolved_codeunit_call_is_extracted(tmp_path):
    management = _write(tmp_path, "Management.Codeunit.al", """
codeunit 1 Management
{
    procedure EnsureSetup()
    begin
    end;
}
""")
    series = _write(tmp_path, "NoSeries.Codeunit.al", """
codeunit 2 "No. Series"
{
}
""")
    setup = _write(tmp_path, "Setup.Page.al", """
page 1 Setup
{
    trigger OnOpenPage()
    begin
        Management.EnsureSetup();
    end;

    var
        Management: Codeunit Management;
}
""")
    list_page = _write(tmp_path, "List.Page.al", """
page 2 List
{
    trigger OnOpenPage()
    begin
        Series.GetNextNo();
    end;

    var
        Series: Codeunit "No. Series";
}
""")

    nodes, edges = _extract_all([management, series, setup, list_page])
    by_id = {node["id"]: node for node in nodes}
    calls = [edge for edge in edges if edge["relation"] == "calls"]

    def call_from(filename):
        return next(
            edge for edge in calls
            if filename in edge.get("source_file", "").replace("\\", "/")
        )

    found = call_from("Setup.Page.al")
    assert by_id[found["source"]]["label"] == ".OnOpenPage()"
    assert by_id[found["target"]]["label"] == ".EnsureSetup()"
    assert found["confidence"] == "EXTRACTED"
    missing = call_from("List.Page.al")
    assert by_id[missing["source"]]["label"] == ".OnOpenPage()"
    assert by_id[missing["target"]]["label"].strip('"') == "No. Series"
    assert missing["confidence"] == "INFERRED"


def test_enum_values_stay_on_the_declaring_object(tmp_path):
    claim = _write(tmp_path, "ClaimStatus.Enum.al", """
enum 1 "Claim Status"
{
    value(0; New) { }
    value(1; "In Progress") { }
}
""")
    other = _write(tmp_path, "OtherStatus.Enum.al", """
enum 2 "Other Status"
{
    value(0; New) { }
}
""")
    extension = _write(tmp_path, "ClaimStatus.EnumExt.al", """
enumextension 3 "Claim Status Ext" extends "Claim Status"
{
    value(10; Reopened) { }
}
""")

    nodes, edges = _extract_all([claim, other, extension])
    by_id = {node["id"]: node for node in nodes}
    values = [node for node in nodes if node.get("_origin") == "al_enum_value"]

    def parent(node):
        return by_id[node["parent"]]["label"].strip('"')

    news = [node for node in values if node["label"] == "New"]
    assert len(news) == 2
    assert {parent(node) for node in news} == {"Claim Status", "Other Status"}
    assert len({node["id"] for node in news}) == 2
    assert all(node["value_id"] == "0" for node in news)
    progress = next(node for node in values if node["label"] == "In Progress")
    assert parent(progress) == "Claim Status"
    assert progress["value_id"] == "1"
    assert progress["source_location"] == "L5"
    reopened = next(node for node in values if node["label"] == "Reopened")
    assert parent(reopened) == "Claim Status Ext"
    assert reopened["value_id"] == "10"
    assert ("Claim Status Ext", "Claim Status", "L2") in {
        (by_id[edge["source"]]["label"].strip('"'), by_id[edge["target"]]["label"].strip('"'), edge["source_location"])
        for edge in edges if edge["relation"] == "extends"
    }
