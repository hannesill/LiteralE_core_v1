from sklearn.cluster import KMeans
from torch.utils.data import Dataset
import os.path as osp
import pandas as pd
import numpy as np
import torch
from tqdm import tqdm
import spacy


class LiteralLinkPredDataset(Dataset):

    def __getitem__(self, index):
        # placeholder
        return None

    def __init__(self, triple_file, transform=None, target_transform=None):
        # Parameters
        self.triple_file = triple_file
        self.embedding_dim = 300  # Mandated by Spacy
        self.transform = transform
        self.target_transform = target_transform

        # Data
        self.df_triples_train, self.df_triples_val, self.df_triples_test, self.df_literals_num, self.df_literals_txt \
            = self.load_dataframes()

        # Relational data
        self.entities, self.relations = self.load_relational_data()

        self.num_entities = len(self.entities)
        self.num_relations = len(self.relations)

        self.entity2id = {self.entities[i]: i for i in range(self.num_entities)}
        self.relation2id = {self.relations[i]: i for i in range(self.num_relations)}

        self.edge_index_train, self.edge_index_val, self.edge_index_test = self.load_edge_indices()
        self.edge_type_train, self.edge_type_val, self.edge_type_test = self.load_edge_types()

        # Literal data
        self.literals_num, self.attr_relations_num = self.load_literals_and_attr_relations_num()
        self.literals_txt, self.attr_relations_txt = self.load_literals_and_attr_relations_txt()

    def load_dataframes(self):
        print('Start loading dataframes')
        df_triples_train = pd.read_csv(osp.join(self.triple_file, 'train.txt'), header=None, sep='\t')
        df_triples_val = pd.read_csv(osp.join(self.triple_file, 'valid.txt'), header=None, sep='\t')
        df_triples_test = pd.read_csv(osp.join(self.triple_file, 'test.txt'), header=None, sep='\t')
        df_literals_num = pd.read_csv(osp.join(self.triple_file, 'numerical_literals.txt'), header=None, sep='\t')
        df_literals_txt = pd.read_csv(osp.join(self.triple_file, 'text_literals.txt'), header=None, sep='\t')

        return df_triples_train, df_triples_val, df_triples_test, df_literals_num, df_literals_txt

    def load_relational_data(self):
        print('Start loading relational data')
        self.entities = list(set(np.concatenate([self.df_triples_train[0].unique(),
                                                 self.df_triples_test[0].unique(),
                                                 self.df_triples_val[0].unique(),
                                                 self.df_triples_train[2].unique(),
                                                 self.df_triples_test[2].unique(),
                                                 self.df_triples_val[2].unique(),
                                                 self.df_literals_num[0].unique(),
                                                 self.df_literals_txt[0].unique()])))

        self.relations = list(set(np.concatenate([self.df_triples_train[1].unique(),
                                                  self.df_triples_test[1].unique(),
                                                  self.df_triples_val[1].unique()])))

        return self.entities, self.relations

    def load_edge_indices(self):
        edge_index_train = torch.stack([torch.tensor(self.df_triples_train[0].map(self.entity2id)),
                                        torch.tensor(self.df_triples_train[2].map(self.entity2id))])
        edge_index_val = torch.stack([torch.tensor(self.df_triples_val[0].map(self.entity2id)),
                                      torch.tensor(self.df_triples_val[2].map(self.entity2id))])
        edge_index_test = torch.stack([torch.tensor(self.df_triples_test[0].map(self.entity2id)),
                                       torch.tensor(self.df_triples_test[2].map(self.entity2id))])

        return edge_index_train, edge_index_val, edge_index_test

    def load_edge_types(self):
        edge_type_train = torch.tensor(self.df_triples_train[1].map(self.relation2id))
        edge_type_val = torch.tensor(self.df_triples_val[1].map(self.relation2id))
        edge_type_test = torch.tensor(self.df_triples_test[1].map(self.relation2id))

        return edge_type_train, edge_type_val, edge_type_test

    def load_literals_and_attr_relations_num(self):
        # with E = number of embeddings, R = number of attributive relations, V = feature dim
        print('Start loading numerical literals: E x R')
        attr_relations_num_unique = list(self.df_literals_num[1].unique())

        print("Unique numerical attributive relations: ", len(attr_relations_num_unique))

        attr_relation_num_2_id = {attr_relations_num_unique[i]: i for i in range(len(attr_relations_num_unique))}

        # Map entities to ids
        self.df_literals_num[0] = self.df_literals_num[0].map(self.entity2id).astype(int)
        # Map attributive relations to ids
        self.df_literals_num[1] = self.df_literals_num[1].map(attr_relation_num_2_id).astype(int)
        # Change literal values to float
        self.df_literals_num[2] = self.df_literals_num[2].astype(float)

        # Extract numerical literal feature vectors for each entity for literal values and attributive relations
        features_num = []
        features_num_attr = []
        for i in tqdm(range(len(self.entities))):
            df_i = self.df_literals_num[self.df_literals_num[0] == i]

            feature_i = torch.zeros(len(attr_relations_num_unique))
            feature_i_attr = torch.zeros(len(attr_relations_num_unique))
            for index, row in df_i.iterrows():
                # Numerical literal values: row[1] = attributive relation index, row[2] = literal value as float
                feature_i[int(row[1])] = float(row[2])

                # One-hot encoding for attributive relations
                feature_i_attr[int(row[1])] = 1

            features_num.append(feature_i)
            features_num_attr.append(feature_i_attr)
        features_num = torch.stack(features_num)
        features_num_attr = torch.stack(features_num_attr)

        # Normalize numerical literals # TODO: Richtig?
        max_lit, min_lit = torch.max(features_num, dim=0).values, torch.min(features_num, dim=0).values
        features_num = (features_num - min_lit) / (max_lit - min_lit + 1e-8)

        return features_num, features_num_attr

    def load_literals_and_attr_relations_txt(self):
        print('Start loading textual literals: E x R x V')
        attr_relations_txt_unique = list(self.df_literals_txt[1].unique())
        attr_relation_txt_2_id = {attr_relations_txt_unique[i]: i for i in range(len(attr_relations_txt_unique))}

        print("Unique textual attributive relations: ", len(attr_relations_txt_unique))

        # Map entities to ids
        self.df_literals_txt[0] = self.df_literals_txt[0].map(self.entity2id).astype(int)
        # Map attributive relations to ids
        self.df_literals_txt[1] = self.df_literals_txt[1].map(attr_relation_txt_2_id).astype(int)
        # Change literal values to string
        self.df_literals_num[2] = self.df_literals_num[2].astype(str)

        nlp = spacy.load('en_core_web_md')

        # Extract embedding vectors for one textual literal value per entity and the attributive relations
        # TODO (optional): Take every literal feature and not just 1 -> take a look at LiteralE original impl
        features_txt = []
        features_txt_attr = []
        for i in tqdm(range(len(self.entities))):
            df_i = self.df_literals_txt[self.df_literals_txt[0] == i]

            features_txt_i = torch.zeros(len(attr_relations_txt_unique), self.embedding_dim)
            features_txt_attr_i = torch.zeros(len(attr_relations_txt_unique))
            for index, row in df_i.iterrows():
                # Textual literal values: row[1] = attributive relation index, row[2] = literal value
                # TODO (optional): BERT embeddings ausprobieren
                spacy_embedding = torch.tensor(nlp(row[2]).vector)
                # TODO: Embedding size spacy mitgebbar?
                features_txt_i[int(row[1])] = spacy_embedding

                # One-hot encoding for attributive relations
                features_txt_attr_i[int(row[1])] = 1

            features_txt.append(features_txt_i)
            features_txt_attr.append(features_txt_attr_i)

        features_txt = torch.stack(features_txt)
        features_txt_attr = torch.stack(features_txt_attr)

        return features_txt.squeeze(), features_txt_attr

    def filter_literals_by_attr_relation_frequency(self, threshold=100):
        print(f"Filtering literals by attributive relation frequency with threshold {threshold}...")
        # Count occurences of attributive relations
        attr_relations_num_counts = self.df_literals_num[1].value_counts()
        attr_relations_txt_counts = self.df_literals_txt[1].value_counts()

        # Filter attributive relations by frequency
        attr_relations_num_filtered = attr_relations_num_counts[attr_relations_num_counts > threshold].index
        attr_relations_txt_filtered = attr_relations_txt_counts[attr_relations_txt_counts > threshold].index

        print(f"Literals num before: {len(attr_relations_num_counts)} after: {len(attr_relations_num_filtered)}")
        print(f"Literals txt before: {len(attr_relations_txt_counts)} after: {len(attr_relations_txt_filtered)}")

        # Filter literals_num and literals_txt
        self.literals_num = self.literals_num[:, attr_relations_num_filtered]
        self.literals_txt = self.literals_txt[:, attr_relations_txt_filtered]

        # Filter attributive relations
        self.attr_relations_num = self.attr_relations_num[attr_relations_num_filtered]
        self.attr_relations_txt = self.attr_relations_txt[attr_relations_txt_filtered]

    def cluster_literals_txt(self, n_clusters=100):
        print(f"Clustering textual literals with {n_clusters} clusters...")
        embeddings = self.literals_txt.numpy()

        embeddings_cluster_labeled = KMeans(n_clusters=n_clusters, random_state=0, n_init=10).fit_predict(embeddings)

        # Convert text literals to one-hot encoding of clusters
        self.literals_txt = torch.zeros(len(self.entities), n_clusters)
        for i in range(len(embeddings_cluster_labeled)):
            self.literals_txt[i, embeddings_cluster_labeled[i]] = 1


if __name__ == '__main__':
    dataset_name = 'fb15k-237'
    if not osp.isfile(f'data/{dataset_name}/processed.pt'):
        print('Process dataset...')
        dataset = LiteralLinkPredDataset(f'data/{dataset_name}')
        torch.save(dataset, f'data/{dataset_name}/processed.pt')

    print("Test variant 2 – filtering")
    dataset = torch.load(f'data/{dataset_name}/processed.pt')

    print(dataset.attr_relations_num.shape)
    print(dataset.attr_relations_txt.shape)
    print(dataset.df_literals_num.shape)
    print(dataset.df_literals_txt.shape)

    dataset.filter_literals_by_attr_relation_frequency()

    print(dataset.attr_relations_num.shape)
    print(dataset.attr_relations_txt.shape)
    print(dataset.df_literals_num.shape)
    print(dataset.df_literals_txt.shape)

    print("Test variant 3 – clustering")

    dataset = torch.load(f'data/{dataset_name}/processed.pt')
    dataset.cluster_literals_txt(20)

    print(dataset.literals_txt.shape)
    print(dataset.literals_txt[0])
