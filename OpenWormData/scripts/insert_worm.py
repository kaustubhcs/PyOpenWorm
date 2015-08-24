from __future__ import print_function
import PyOpenWorm as P
import traceback
import sqlite3

SQLITE_DB_LOC = '../aux_data/celegans.db'
LINEAGE_LIST_LOC = '../aux_data/C. elegans Cell List - WormAtlas.tsv'

def serialize_as_n3():
    dest = '../WormData.n3'
    # XXX: Properties aren't initialized until the first object of a class is created,
    #      so we create them here

    for x in dir(P):
        if isinstance(getattr(P, x), type) and issubclass(getattr(P, x), P.DataObject):
            c = getattr(P, x)
            if x == 'values':
                c("dummy")
            else:
                c()
    P.config('rdf.graph').serialize(dest, format='n3')
    print('serialized to n3 file')

def upload_muscles():
    """ Upload muscles and the neurons that connect to them
    """
    try:
        ev = P.Evidence(title="C. elegans sqlite database")
        conn = sqlite3.connect(SQLITE_DB_LOC)
        cur = conn.cursor()
        w = P.Worm()
        cur.execute("""
        SELECT DISTINCT a.Entity, b.Entity
        FROM tblrelationship innervatedBy, tblentity b, tblentity a, tblrelationship type_b
        WHERE innervatedBy.EnID1=a.id and innervatedBy.Relation = '1516' and innervatedBy.EnID2=b.id
        and type_b.EnID1 = b.id and type_b.Relation='1515' and type_b.EnID2='1519'
        """) # 1519 is the
        for r in cur.fetchall():
            neuron_name = str(r[0])
            muscle_name = str(r[1])
            m = P.Muscle(muscle_name)
            n = P.Neuron(neuron_name)
            w.muscle(m)
            m.innervatedBy(n)

        ev.asserts(w)
        ev.save()
        #second step, get the relationships between them and add them to the graph
        print ("uploaded muscles")
    except Exception:
        traceback.print_exc()
    finally:
        conn.close()

def upload_lineage_and_descriptions():
    """ Upload lineage names and descriptions pulled from the WormAtlas master cell list

    Assumes that Neurons and Muscles have already been added
    """
    # XXX: This wants a way to insert cells, then later, to insert neurons from the same set
    # and have the later recoginzed as the former. Identifier matching limits us here. It would
    # be best to establish owl:sameAs links to the super class (Cell) from the subclass (Neuron)
    # at the sub-class insert and have a reasoner relate
    # the two sets of inserts.
    cells = dict()
    try:
        w = P.Worm()
        net = w.neuron_network.one()
        ev = P.Evidence(uri="http://www.wormatlas.org/celllist.htm")
        # insert neurons.
        # save
        cell_data = open(LINEAGE_LIST_LOC, "r")

        # Skip headers
        next(cell_data)

        cell_name_counters = dict()
        data = dict()
        for x in cell_data:
             j = [x.strip().strip("\"") for x in x.split("\t")]
             name = j[0]
             lineageName = j[1]
             desc = j[2]

             # XXX: These renaming choices are arbitrary and may be inappropriate
             if name == "DB1/3":
                 name = "DB1"
             elif name == "DB3/1":
                 name = "DB3"
             elif name == "AVFL/R":
                 if lineageName[0] == "W":
                     name = "AVFL"
                 elif lineageName[0] == "P":
                     name = "AVFR"

             if name in cell_name_counters:
                 while (name in cell_name_counters):
                     cell_name_counters[name] += 1
                     name = name + "("+ str(cell_name_counters[name]) +")"
             else:
                 cell_name_counters[name] = 0

             data[name] = {"lineageName" : lineageName, "desc": desc}

        def add_data_to_cell(n):
            name = n.name.one()
            cell_data = data[str(name)]
            n.lineageName(cell_data['lineageName'])
            n.description(cell_data['desc'])
            w.cell(n)

        for n in net.neuron():
            add_data_to_cell(n)

        # TODO: Add data for other cells here. Requires relating named
        # muscle cells to their counterparts in the cell list (e.g. mu_bod(#))
        # Also requires removing neurons and muscles from the list once
        # they've been identified so they aren't stored twice

        ev.asserts(w)
        ev.save()
        print ("uploaded lineage and descriptions")
    except Exception, e:
        traceback.print_exc()

def norn(x):
    """ return the next or None of an iterator """
    try:
        return next(x)
    except StopIteration:
        return None

def upload_neurons():
    try:
        conn = sqlite3.connect(SQLITE_DB_LOC)
        cur = conn.cursor()
        ev = P.Evidence(title="C. elegans sqlite database")
        w = P.Worm()
        n = P.Network()
        w.neuron_network(n)
        # insert neurons.
        # save
        cur.execute("""
        SELECT DISTINCT a.Entity FROM tblrelationship, tblentity a, tblentity b
        where EnID1=a.id and Relation = '1515' and EnID2='1'
        """)
        for r in cur.fetchall():
            neuron_name = str(r[0])
            n.neuron(P.Neuron(name=neuron_name))
        ev.asserts(n)
        ev.save()
        #second step, get the relationships between them and add them to the graph
        print ("uploaded neurons")
    except Exception:
        traceback.print_exc()
    finally:
        conn.close()

def get_altun_evidence():
    return parse_bibtex_into_evidence('../aux_data/bibtex_files/altun2009.bib')

def get_wormatlas_evidence():
    return parse_bibtex_into_evidence('../aux_data/bibtex_files/WormAtlas.bib')

def parse_bibtex_into_evidence(file_name):
    import bibtexparser
    e = P.Evidence()
    with open(file_name) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)

        try:
            doi = bib_database.entries[0]['doi']
            if doi:
              e.doi(doi)
        except KeyError:
            pass

        try:
            author = bib_database.entries[0]['author']
            if author:
              e.author(author)
        except KeyError:
            pass

        try:
            title = bib_database.entries[0]['title']
            if title:
              e.title(title)
        except KeyError:
            pass
        try:
            year = bib_database.entries[0]['year']
            if year:
              e.year(year)
        except KeyError:
            pass
        e.save()
    return e

def upload_receptors_types_neurotransmitters_neuropeptides_innexins():
    """ Augment the metadata about neurons with information about receptors,
        neuron types, neurotransmitters, neuropeptides and innexins.
        As we go, add evidence objects to each statement."""
    print ("uploading statements about types, receptors, innexins, neurotransmitters and neuropeptides")

    #set up evidence objects in advance
    altun_ev  = get_altun_evidence()
    wormatlas_ev = get_wormatlas_evidence();

    import csv, sys
    f = open('../aux_data/Modified celegans db dump.csv')
    reader = csv.reader(f)
    reader.next() #skip the header row

    i = 0

    for row in reader:
      neuron_name = row[0]
      relation = row[1].lower()
      data = row[2]
      evidence = row[3]
      evidenceURL = row[4]

      #prepare evidence
      e = P.Evidence()

      #pick correct evidence given the row
      if 'altun' in evidence.lower():
          altun_ev.uri(evidenceURL)
          e = altun_ev

      elif 'wormatlas' in evidence.lower():
          wormatlas_ev.uri(evidenceURL)
          e = wormatlas_ev

      #grab the neuron object
      n = P.Neuron(name=neuron_name)

      if relation == 'neurotransmitter':
          # assign the data, grab the relation into r
          r = n.neurotransmitter(data)
          #assert the evidence on the relationship
          e.asserts(r)
      elif relation == 'innexin':
          # assign the data, grab the relation into r
          r = n.innexin(data)
          #assert the evidence on the relationship
          e.asserts(r)
      elif relation == 'neuropeptide':
          # assign the data, grab the relation into r
          r = n.neuropeptide(data)
          #assert the evidence on the relationship
          e.asserts(r)
      elif relation == 'receptor':
          # assign the data, grab the relation into r
          r = n.receptor(data)
          #assert the evidence on the relationship
          e.asserts(r)

      if relation == 'type':
          types = []
          if 'sensory' in (data.lower()):
              types.append('sensory')
          if 'interneuron' in (data.lower()):
              types.append('interneuron')
          if 'motor' in (data.lower()):
              types.append('motor')
          # assign the data, grab the relation into r
          for t in types:
              r = n.type(t)
              #assert the evidence on the relationship
              e.asserts(r)

      i = i + 1
      print(str(i) + '.')
    altun_ev.save()
    wormatlas_ev.save()
    print ("uploaded " + str(i) + " statements about types, receptors, innexins, neurotransmitters and neuropeptides")


def new_connections():
    """we can replace the old function (upload_connections) with this
    once it is ready to go"""

    import re
    search_string = re.compile(r'\w+[0]+[1-9]+')
    replace_string = re.compile(r'[0]+')

    def normalize(name):
        # normalize neuron names to match those used at other points
        # see #137 for elaboration
        # if there are zeroes in the middle of a name, remove them
        if re.match(search_string, name):
            name = replace_string.sub('', name)
        return name


    try:
        w = P.Worm()
        n = P.Network()
        neurons = set(n.neurons())
        w.neuron_network(n)

        # Evidence object to assert each connection
        e  = P.Evidence(uri='http://www.wormwiring.org')

        with open('../aux_data/herm_full_edgelist.csv', 'rb') as csvfile:
            edge_reader = csv.reader(csvfile)
            edge_reader.next()    # skip header row
            for row in edge_reader:
                source, target, weight, syn_type = map(str.strip, row)

                # set synapse type to something the Connection object
                # expects, and normalize the source and target names
                if syn_type == 'electrical':
                    syn_type = 'gapJunction'
                elif syn_type == 'chemical':
                    syn_type = 'send'
                source = normalize(source)
                target = normalize(target)
                if source in neurons and target in neurons:
                    c = P.connection(
                        pre_cell=source, post_cell=target,
                        number=weight, syntype=syn_type
                    )

                    n.synapse(c)
                    e.asserts(c)

        e.asserts(n) # assert the whole connectome too
        e.save()
        print('uploaded connections')

    except Exception, e:
        traceback.print_exc()


def upload_connections():
    import re
    search_string = re.compile(r'\w+[0]+[1-9]+')
    replace_string = re.compile(r'[0]+')

    def normalize(name):
        # normalize neuron names to match those used at other points
        # see #137 for elaboration
        # if there are zeroes in the middle of a name, remove them
        if re.match(search_string, name):
            name = replace_string.sub('', name)
        return name

    import xlrd

    try:
        w = P.Worm()
        n = P.Network()
        w.neuron_network(n)
        combining_dict = {}
        # Get synapses and gap junctions and add them to the graph
        s = xlrd.open_workbook('../aux_data/NeuronConnect.xls').sheets()[0]
        for row in range(1, s.nrows):
            if s.cell(row, 2).value in ('S', 'Sp', 'EJ'):
                #We're not going to include 'receives' ('R', 'Rp') since they're just the inverse of 'sends'
                #Also omitting 'NMJ' for the time being (no model in db)
                pre = normalize(s.cell(row, 0).value)
                post = normalize(s.cell(row, 1).value)
                num = int(s.cell(row, 3).value)
                if s.cell(row, 2).value == 'EJ':
                    syntype = 'gapJunction'
                elif s.cell(row, 2).value in ('S', 'Sp'):
                    syntype = 'send'

                # Add them to a dict to make sure Sends ('S') and Send-polys ('Sp') are summed.
                # keying by connection pairs as a string (e.g. 'SDQL,AVAL,send').
                # values are lists of the form [pre, post, number, syntype].
                string_key = '{},{},{}'.format(pre, post, syntype)
                if string_key in combining_dict.keys():
                    # if key already there, add to number
                    num += combining_dict[string_key][2]

                combining_dict[string_key] = [pre, post, num, syntype]

        for entry in combining_dict:
            pre, post, num, syntype = combining_dict[entry]
            c = P.Connection(pre_cell=pre, post_cell=post, number=num, syntype=syntype)
            n.synapse(c)

        e = P.Evidence(uri='http://www.wormatlas.org/neuronalwiring.html#Connectivitydata')
        e.asserts(n)
        e.save()
        print('uploaded connections')
    except Exception, e:
        traceback.print_exc()

def infer():
    from rdflib import Graph
    from FuXi.Rete.RuleStore import SetupRuleStore
    from FuXi.Rete.Util import generateTokenSet
    from FuXi.Horn.HornRules import HornFromN3

    try:
        w = P.Worm()
        semnet = w.rdf #fetches the entire worm.db graph

        rule_store, rule_graph, network = SetupRuleStore(makeNetwork=True)
        closureDeltaGraph = Graph()
        network.inferredFacts = closureDeltaGraph

        #build a network of rules
        for rule in HornFromN3('inference_rules.n3'):
            network.buildNetworkFromClause(rule)

        network.feedFactsToAdd(generateTokenSet(semnet)) # apply rules to original facts to infer new facts

        # combine original facts with inferred facts
        for x in closureDeltaGraph:
            w.rdf.add(x)

        ###uncomment next 4 lines to print inferred facts to human-readable file (demo purposes)
        #inferred_facts = closureDeltaGraph.serialize(format='n3') #format inferred facts to notation 3
        #inferred = open('what_was_inferred.n3', 'w')
        #inferred.write(inferred_facts)
        #inferred.close()

    except Exception, e:
        traceback.print_exc()
    print ("filled in with inferred data")

def do_insert(config="default.conf", logging=False):
    if config:
        if isinstance(config, P.Configure):
            pass
        elif isinstance(config, str):
            config = P.Configure.open(config)
        elif isinstance(config, dict):
            config = P.Configure().copy(config)
        else:
            raise Exception("Invalid configuration object "+ str(config))

    P.connect(conf=config, do_logging=logging)
    try:
        w = P.Worm()
        net = P.Network()
        w.neuron_network(net)
        w.save()

        upload_neurons()
        upload_muscles()
        upload_receptors_types_neurotransmitters_neuropeptides_innexins()
        upload_lineage_and_descriptions()
        upload_connections()
        serialize_as_n3()
        infer()
    except:
        traceback.print_exc()
    finally:
        P.disconnect()

if __name__ == '__main__':
    # NOTE: This process will NOT clear out the database if run multiple times.
    #       Multiple runs will add the data again and again.
    # Takes about 5 minutes with ZODB FileStorage store
    # Takes about 3 minutes with Sleepycat store
    import sys
    import os
    logging = False
    if len(sys.argv) > 1 and sys.argv[1] == '-l':
        logging = True
    try:
        do_insert(logging=logging)
    except IOError as e:
        if e.errno == 2 and 'default.conf' in e.filename:
            print("Couldn't find the 'default.conf' configuration file. You may have attempted to run this script in the wrong directory")
