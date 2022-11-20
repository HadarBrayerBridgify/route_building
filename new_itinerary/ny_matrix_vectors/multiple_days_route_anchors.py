import re
import gmplot
import random
import string
import json
import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from sklearn.preprocessing import StandardScaler
from itertools import combinations
from typing import Any, Dict, List
from datetime import datetime, date, timedelta
import time

import data_preprocessing as dp
import restaurants as rest
from typing import Dict, List, Tuple


# import restaurants as rest


# new data preprocessing


# class Anchors:
#
#     def __init__(self,
#                  anchors: Dict):  # (anchors= {date: {uuid: hour}, date: {uuid:hour})     (anchors= {uuid: (date,hour)})
#
#         self.anchors = dict(sorted(anchors.items(), key=lambda x: x[1]))
#         self.uuids = list(self.anchors.keys())
#         self.position_list = list(self.anchors.values())
#         self.num_anchors = len(anchors)
#
#     def duration_between(self, position1, position2):
#         return abs(position2 - position1)
#
#     def duration_before(self, start_hour):
#         """
#         Args:
#             start_hour: float. hour of starting the day trip (After breakfast)
#         return:
#             duration before the first anchore
#         """
#         return min(self.position_list) - start_hour
#
#     def duration_after(self, end_hour):
#         return end_hour - max(self.position_list)


##### route with restaurants
class RouteBulider:

    def __init__(self, df, chosen_tags, df_similarity_norm, df_distances, tot_num_attractions,
                 weight_dict, user_dates, availability_df, anchors=None):
        self.df = df
        self.problematic_uuids = self.find_nan_attractions_uuid()
        # self.tags_vec = tags_vec
        self.chosen_tags = chosen_tags
        self.popularity_vec = self.create_popularity_vec()
        self.df_similarity_norm = df_similarity_norm
        self.df_similarity_standard = self.standard_scaler(df_similarity_norm)
        self.df_distances = df_distances
        self.df_distances_standard = self.standard_scaler(self.df_distances)
        self.df_distances_norm = self.norm_df(self.df_distances)
        self.tot_attractions_duration = tot_num_attractions
        self.weight_dict = weight_dict
        self.user_dates = user_dates
        self.availability_df = availability_df
        self.availability_user_dates_dict = self.availability_user_dates()
        self.availability_per_date = None
        self.anchors = anchors
        if self.anchors:
            self.anchors_uuids = self.extract_anchors_uuids()

        self.current_anchors = dict()
        self.chosen_idx = list()  # np.nan(self.tot_num_attractions)
        self.similarity_vec = 0
        self.distance_vec = None
        self.tags_vec = None
        self.duration_vec = self.create_duration_vec()
        self.duration_vec_norm = None
        self.paid_attrac_vec = None
        self.availability_vec = None
        # if len(self.chosen_idx) > 0:
        #     self.last_idx = self.chosen_idx[-1]
        self.sum_duration = 0
        self.duration_paid_attrac = 0
        self.final_route_df = pd.DataFrame()

        self.df_similarity_norm.columns = self.df_similarity_norm.index
        self.all_days_attractions_idx = list()
        self.all_days_restaurants_idx = list()

    def standard_scaler(self, df):
        scaler = StandardScaler()
        df_standard = pd.DataFrame(scaler.fit_transform(df))
        df_standard.index = df.index
        df_standard.columns = df.columns
        return df_standard

    def extract_anchors_uuids(self):
        """
        Return: list of the uuids of the anchors
        """
        uuids_lists = np.array([i.keys() for i in self.anchors.values()])
        anchors_uuids = []
        for uuids in uuids_lists:
            for u in uuids:
                anchors_uuids.append(u)
        return anchors_uuids

    def find_nan_attractions_uuid(self) -> List[str]:
        """
        Extract the uuids without 'title' and 'description'

        Return:
            list of uuids
        """
        empty_title = self.df["uuid"][self.df["title"] == ""].values
        return empty_title

    def first_attraction(self):
        """
        return the first attraction according to 2*popularity and chosen tags
        """
        vec_result = (self.tags_vec + 2 * self.popularity_vec) * self.availability_vec
        duplicates = []
        for idx in self.all_days_attractions_idx:
            duplicates += self.drop_too_similar(idx)
        idx_to_drop = duplicates + self.all_days_attractions_idx
        vec_result = vec_result.drop(index=idx_to_drop)
        vec_result = vec_result[vec_result.values != 0]
        vec_sorted = vec_result.sort_values()
        self.chosen_idx = [vec_result.sort_values().index[0]]



    def drop_too_similar(self, idx):
        max_similarity_threshold = 0.69
        min_similarity_threshold = 0.45
        distance_threshold = 0.1
        duplicates = list(
            self.df_similarity_norm.loc[idx][self.df_similarity_norm.loc[idx] > max_similarity_threshold].index)
        min_similarity_attractions = set(self.df_similarity_norm.loc[idx][self.df_similarity_norm.loc[idx] > min_similarity_threshold].index)
        similarity_by_location = set(self.df_distances.loc[idx][self.df_distances.loc[idx] < distance_threshold].index)
        duplicates += list(min_similarity_attractions & similarity_by_location)
        return duplicates


    def vec_scaling(self, vec):
        chosen_median = 0.5
        difference = chosen_median // vec.median()
        if difference:
            return vec * difference
        else:
            return vec

    def attractions_score_vec(self, idx_to_drop):
        """
        return a vector with a score for every attraction according to the last chosen attraction/s
        """
        vectors_results = (
                                  (self.weight_dict["popular"] * self.popularity_vec) +
                                  (self.weight_dict["distance"] * self.distance_vec) +
                                  (self.weight_dict["similarity"] * self.similarity_vec)) *\
        self.tags_vec * self.duration_vec_norm * self.availability_vec * self.paid_attrac_vec


        # print("vector results with zeros:", self.vec_scaling(self.popularity_vec).sort_values())
        print("popular vec:\n", self.popularity_vec.sort_values()[:10], self.popularity_vec.shape)
        print("distance vec:\n", self.distance_vec.sort_values()[:10], self.distance_vec.shape)
        print("similarity vec:\n", self.similarity_vec.sort_values()[:10], self.similarity_vec.shape)
        print("tags vec:\n", self.tags_vec.sort_values()[:10])

        # drop duplicates of the chosen uuids
        duplicates_idx = list()
        idx_to_drop = list(set(self.all_days_attractions_idx + idx_to_drop))
        for idx in idx_to_drop:
            duplicates = self.drop_too_similar(idx)
            if len(duplicates) > 1:
                duplicates.remove(idx)
                duplicates_idx += duplicates
        idx_to_drop += duplicates_idx

        # remove problematic attractions #
        relevant_uuids = list(set(vectors_results.index) - set(self.problematic_uuids))
        vectors_results = vectors_results.loc[relevant_uuids]
        idx_to_drop = list(set(idx_to_drop) - set(self.problematic_uuids))
        # drop chosen uuids and their duplicates
        #idx_to_drop = list(set(idx_to_drop + self.all_days_attractions_idx))
        vectors_results.drop(index=idx_to_drop, inplace=True)
        vectors_results = vectors_results[vectors_results.values != 0]
        vectors_results.dropna(inplace=True)
        return vectors_results

    def next_best(self, score_vector):
        """
        input: Vector with the score of each attraction according to the last chosen attraction
        output: the next best attraction/s
        """
        print("vector results\n", score_vector.sort_values()[:5])
        try:
            test_score = score_vector.sort_values()
            return score_vector.sort_values().index[0]
        except IndexError:
            print("Sorry, could not find available attractions!")

    def df_tags(self):
        """
        Creating DataFrame for all tags (each tag will have a different column)
        """

        tags_dict = {tag: [] for tag in self.chosen_tags}
        for tag_name in tags_dict.keys():
            for tags in self.df["categories_list"]:
                if tag_name in tags:
                    tags_dict[tag_name].append(1)
                else:
                    tags_dict[tag_name].append(0)
        tags_df = pd.DataFrame(tags_dict)
        tags_df.index = self.df["uuid"]
        return tags_df

    def create_popularity_vec(self):
        df = self.df.set_index("uuid")
        df["popularity_norm"] = None
        for supplier in df["inventory_supplier"].unique():
            uuids = df[df["inventory_supplier"] == supplier].index
            max_reviews = df["number_of_reviews"].loc[uuids].sort_values(ascending=False).values[0]
            if max_reviews == 0:
                max_reviews = 1

            df["popularity_norm"].loc[uuids] = df["number_of_reviews"].loc[uuids].apply(lambda x: x / max_reviews)
        df["popularity_norm"] = df["popularity_norm"].fillna(0)

        # attrac_with_reviews = df["popularity_norm"][df["popularity_norm"] != 0].sort_values()
        # attrac_without_reviews = df["popularity_norm"][df["popularity_norm"] == 0]
        # num_attrac_with_reviews = len(attrac_with_reviews)
        # norm_values = np.arange(0, 1 + 0.5 * (1 / (num_attrac_with_reviews - 1)), 1 / (num_attrac_with_reviews - 1))
        # df["popularity_norm"].loc[attrac_with_reviews.index] = norm_values
        # df["popularity_norm"].loc[attrac_without_reviews.index] = 0.8
        df["popularity_norm"] = 1 - df["popularity_norm"]

        scaler = StandardScaler()
        df["popularity_norm"] = scaler.fit_transform(pd.DataFrame(df["popularity_norm"]))
        return df["popularity_norm"].squeeze()

    def update_tags_vec(self, chosen_idx):

        # creating a dataframe for the chosen tags
        tags_df = self.df_tags()

        # reduce the values of the tags that already been chosen
        if len(chosen_idx) > 0:

            # checking how many times each 'chosen tag' has been chosen
            selected_tags_count = tags_df.loc[chosen_idx].sum()

            # Consider only those above 0
            selected_tags_count = selected_tags_count[selected_tags_count > 0]

            for i in range(selected_tags_count.shape[0]):
                tag_name = selected_tags_count.index[i]
                tag_value = selected_tags_count.values[i]
                tags_df[tag_name] = tags_df[tag_name] * (1 / (2 * tag_value))

        # sum the tags to a vector
        tags_sum = tags_df.sum(axis=1)

        # normalized the vector to be between 0-1. transforming the results with '1-norm' in order for the best attraction in terms of tags to be the lowest. Adding 0.01 in order not to reset the results
        self.tags_vec = 1 - self.norm_df(tags_sum) + 0.01
        self.tags_vec.index = self.df["uuid"]

    def norm_df(self, df):
        return (df - df.min()) / (df.max() - df.min())

    def current_similarity_vec(self, chosen_idx):
        """
        Return the similarity vector associated with the last attraction along with the other selected attractions
        """
        current_similarity_vec = self.df_similarity_standard.loc[chosen_idx[-1]]
        current_similarity_vec.index = self.df["uuid"]
        self.similarity_vec = current_similarity_vec + (1 / 3) * self.similarity_vec

    def update_distance_vec(self, chosen_idx):
        self.distance_vec = self.df_distances_standard.loc[chosen_idx[-1]]
        self.distance_vec.index = self.df["uuid"]
        self.distance_vec.fillna(1, inplace=True)

    def create_duration_vec(self):
        def str_to_hours(hour_string):
            try:
                t = datetime.strptime(hour_string, "%H:%M:%S")
                delta = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
                hour = delta.seconds / 3600
                # if the duration is weird, probably it's transportation
                remainder = str(hour)
                if len(remainder) > 4:
                    return 0
                else:
                    return hour
            except:
                return float(hour_string[:2])

        self.df["hour"] = self.df["duration"].apply(lambda x: str_to_hours(x))
        duration_vec = self.df[["uuid", "hour"]].set_index("uuid", drop=True)
        return duration_vec

    def create_availability_vec(self, hour: int, reverse=False) -> Series:
        """
        Create availability vector

        Args:
             hour: float. The hour to check availability or if reverse=True, the hour of the anchore
        """
        self.availability_per_date["availability_vec"] = None
        if reverse:
            self.availability_per_date["availability_hour"] = self.availability_per_date["hour"].apply(
                lambda x: round(hour - x))
            for i in range(self.availability_per_date.shape[0]):
                col = self.availability_per_date["availability_hour"].iloc[i]
                if not 8 < col < 23:
                    self.availability_per_date["availability_vec"].iloc[i] = 0
                else:
                    self.availability_per_date["availability_vec"].iloc[i] = self.availability_per_date[col].iloc[i]
            return self.availability_per_date["availability_vec"]
        else:
            return self.availability_per_date[hour]

    def create_duration_vec_norm(self, chosen_idx):
        time_left = (self.tot_attractions_duration - self.sum_duration) + 0.5
        return self.duration_vec["hour"].apply(lambda x: 1 if x <= time_left and x != 0 else 0)

    def create_paid_attractions_vec(self):
        """
        return 1 for 'google', 0.8 or 0 for 'paid'
        we want paid attractions to be till half of the daily route duration
        return: Series, vector for paid attractions duration. 0: if not relevant, 1:if free(google), 0.5: if paid and relevant
        """
        df = self.df.set_index("uuid", drop=True)
        # we want paid attractions to be till half of the daily route duration
        time_left_for_paid_attractions = self.tot_attractions_duration / 2 - self.duration_paid_attrac
        df["if_google"] = df["inventory_supplier"].apply(lambda x: 1 if x == 'GoogleMaps' else 0.2)
        df["paid_duration"] = df["hour"].apply(lambda x: 1 if x <= time_left_for_paid_attractions else 1.2)
        df["if_paid_results"] = df["if_google"] + df["paid_duration"]
        df["paid_attraction_vec_final"] = df["if_paid_results"].apply(
            lambda x: 1 if x >= 2 else (0.8 if x == 1.2 else 1.2))
        return df["paid_attraction_vec_final"]



    def update_paid_attrac_duration(self, chosen_uuid):
        df = self.df.copy()
        df.set_index("uuid", drop=True, inplace=True)
        if df.loc[chosen_uuid]["inventory_supplier"].values != 'GoogleMaps':
            print(df[["title", "hour"]].loc[chosen_uuid])
            self.duration_paid_attrac += df.loc[chosen_uuid]["hour"].values[0]
            print("paid attractions durations:", self.duration_paid_attrac)

    def update_vectors(self, chosen_uuids, hour, reverse=False):
        """
        update the vectors according to chosen_idx (according to the attractions that were chosen)
        """
        hour = round(hour)
        # update the tags_vector
        self.update_tags_vec(chosen_uuids)
        # find similarity_vec according to current attraction
        self.current_similarity_vec(chosen_uuids)
        # similarity_vec = current_similarity_vec(chosen_idx, df_similarity_norm)
        self.similarity_vec = self.norm_df(self.similarity_vec)
        # extract distance vector
        self.update_distance_vec(chosen_uuids)

        # duration vector norm
        self.duration_vec_norm = self.create_duration_vec_norm(chosen_uuids)
        self.paid_attrac_vec = self.create_paid_attractions_vec()
        # self.availability_vec = self.availability_per_date[hour]
        self.availability_vec = self.create_availability_vec(hour, reverse)
        print("Successfully updated vectors!")
        self.create_vectors_df()

    def create_vectors_df(self):
        #self.vectors_df = pd.DataFrame(self.tags_vec, columns=["tags"])
        self.vectors_df = pd.concat([self.tags_vec, self.similarity_vec, self.distance_vec, self.popularity_vec, self.duration_vec_norm, self.paid_attrac_vec, self.availability_vec], axis=1)
        self.vectors_df.columns = ["tag_vec", "similarity_vec", "distance_vec", "popularity_vec", "duration_vec", "paid_attrac_vec", "availability_vec"]
        self.vectors_df.sort_values(by='distance_vec', inplace=True)
        a = self.vectors_df.loc["f9c068d8-5209-4893-80d2-9d32abba2754"]



    def update_sum_duration(self, chosen_uuid) -> None:
        print("*******sum duration before adding new attraction******:", self.sum_duration)
        if not chosen_uuid[0]:
            self.sum_duration = self.tot_attractions_duration
        else:
            df = self.df.copy()
            df.set_index("uuid", drop=True, inplace=True)
            print("added time:", df.loc[chosen_uuid]["hour"].values[0])
            self.sum_duration += df.loc[chosen_uuid]["hour"].values[0]
            print("*******sum duration after adding new attraction******:", self.sum_duration)

    def availability_user_dates(self) -> Dict[timedelta, DataFrame]:
        """
        Create a dictionary with the user dates as keys and availability dataframe for each date as a value

        Return:
            a dictionary with the user dates as keys and availability dataframe for each date as a value
        """

        def convert_time(time_string):
            date_var = time.strptime(time_string, "%H:%M:%S")
            return date_var.tm_hour

        def convert_date(date_str):
            return datetime.strptime(date_str, "%Y-%m-%d")

        # create a new column with the hour as an int
        self.availability_df["hour"] = self.availability_df["time"].apply(lambda x: convert_time(x))
        # create a new column of formatted date
        self.availability_df["formatted_date"] = self.availability_df["date"].apply(lambda x: convert_date(x))


        # list of all the id attractions
        list_attractions_id = self.availability_df["attraction_id"].unique()

        # empty dict of the user dates and their availability matrices
        availability_dict = {date: None for date in self.user_dates}
        hours = sorted(self.availability_df["hour"].unique())

        for date in self.user_dates:

            # define a matrix with a column of the attractions id
            availability_per_date = pd.DataFrame(list_attractions_id, columns=["attraction_id"])

            for hour in hours:
                # extract the selected date and hour from the original availability dataframe
                hour_availability = self.availability_df[["date", "attraction_id", "hour"]][
                    (self.availability_df['formatted_date'] == date) & (
                                self.availability_df["hour"] == hour)].drop_duplicates()
                hour_availability[hour] = 1
                # merge the specific hour to availability_per_date
                availability_per_date = pd.merge(availability_per_date, hour_availability, how='left')
                availability_per_date.fillna(0, inplace=True)
                availability_per_date.drop(columns=["date", "hour"], inplace=True)
                # availability_per_date.rename(columns={0: 24}, inplace=True)

            # insert the matrix to the dictionary as a value for its date
            availability_dict[date] = availability_per_date
        return availability_dict

    def availability_df_per_date(self, date: str) -> DataFrame:
        specific_date_availability = self.availability_user_dates_dict[date]
        specific_date_availability = specific_date_availability.merge(self.df[["uuid", "categories_list"]], how="outer",
                                                                      left_on="attraction_id", right_on='uuid')
        specific_date_availability.drop(columns="attraction_id", inplace=True)
        specific_date_availability.fillna(1, inplace=True)
        specific_date_availability = specific_date_availability.merge(self.df[["uuid", "hour"]], how="inner", on="uuid")
        specific_date_availability = self.drop_tags_from_availability(specific_date_availability)
        specific_date_availability.set_index("uuid", drop=True, inplace=True)
        return specific_date_availability

    def drop_tags_from_availability(self, daily_availability_df):
        """
        Reset availability of specific categories at certain hours

        Args:
             daily_availability_df: DataFrame. daily data of availability with "categories_list" column

        Return:
            daily availability df with zeros in the specified tags and columns
        """
        day_tags_availability = ["Beach", "Watersports"]
        for i in range(len(daily_availability_df)):
            if i == 1913:
                print(daily_availability_df["categories_list"].iloc[i])
                print(len(daily_availability_df["categories_list"].iloc[i]))
                print("Transportation" in daily_availability_df["categories_list"].iloc[i])
            for tag in day_tags_availability:
                if tag in daily_availability_df["categories_list"].iloc[i]:
                    daily_availability_df[daily_availability_df.columns[15:]].iloc[i] = 0
            if "Nightlife" in daily_availability_df["categories_list"].iloc[i]:
                daily_availability_df[daily_availability_df.columns[1:19]].iloc[i] = 0
            if len(daily_availability_df["categories_list"].iloc[i]) == 1 and "Transportation" in \
                    daily_availability_df["categories_list"].iloc[i]:
                daily_availability_df[daily_availability_df.columns].iloc[i] = 0
        return daily_availability_df

    def extract_similar_attractions(self, uuid):
        return self.df_similarity_norm.loc[uuid][self.df_similarity_norm.loc[uuid] < 1].sort_values(ascending=False)[
               :5].index

    def select_attractions_idx(self, start_attractions, end_attractions, chosen_uuid,
                               uuids_to_drop, reverse_order=False):  # idx_to_drop was added mainly for the anchors
        """
        choose the order and the uuids of the attractions of the route

        Args:
             start_attractions: Float. The time from which we will select the attractions
             end_attractions: Float. The time when we will finish choosing the attractions
             chosen_uuid: str. first selected uuid
             uuids_to_drop: List. List of uuids that the algorithm will not choose

        Return:
            List of selected uuids (ordered) for the route
        """


        df = self.df.set_index("uuid", drop=True)
        #duration = self.tot_attractions_duration - self.sum_duration
        route_duration = True
        #while duration >= 1:
        while route_duration:
            if not reverse_order:
                attraction_time = round(self.final_route_df["end"].values[-1] + 0.5)
                if attraction_time >= end_attractions - 0.5:
                    return chosen_uuid
            else:
                attraction_time = round(self.final_route_df["start"].values[-1] - 0.5)
                if attraction_time <= start_attractions + 0.5:
                    #route_duration = False
                    return chosen_uuid

            self.update_vectors(chosen_uuid, attraction_time, reverse_order)

            vector_results = self.attractions_score_vec(uuids_to_drop)
            attraction_uuid = self.next_best(vector_results)

            # if no attractions available (are not relevant by the algorithm, for example, too similar to other chosen attractions or not available)
            if not attraction_uuid:
                return chosen_uuid
            # append the next index to the indices list
            chosen_uuid.append(attraction_uuid)
            print("chosen_idx:", chosen_uuid)
            uuids_to_drop.append(attraction_uuid)
            self.update_sum_duration([attraction_uuid])
            self.update_paid_attrac_duration([attraction_uuid])
            #duration -= df.loc[attraction_uuid]["hour"] + 0.5
            # add the attraction to the final route
            self.final_route_df = self.uuid_to_df([attraction_uuid], self.final_route_df, start_hour=None,
                                                  reverse=reverse_order)
            # self.final_route_df.sort_values(by="start", inplace=True)

        return chosen_uuid

    def route_without_anchors(self):
        """
        return idx list of the chosen attractions
        """
        self.update_tags_vec([])
        self.availability_vec = self.availability_per_date[9]
        self.first_attraction()
        self.final_route_df = self.uuid_to_df(self.chosen_idx, self.final_route_df)

        # drop the already selected attraction from the list of attractions (self.chosen_idx)
        idx_to_drop = self.chosen_idx.copy()
        self.update_sum_duration(self.chosen_idx)
        self.update_paid_attrac_duration(self.chosen_idx)
        start_hour = self.final_route_df['end'].values[0]
        #duration = self.tot_attractions_duration - self.sum_duration
        end_hour = 20
        return self.select_attractions_idx(start_hour, end_hour, self.chosen_idx, idx_to_drop)

    def create_full_route(self, rest_instance=None):
        df_uuid = self.df.set_index("uuid", drop=True)
        route_dict = dict()
        for i in range(len(self.user_dates)):
            if i == 1:
                print("day 2")
            self.availability_per_date = self.availability_df_per_date(self.user_dates[i])
            if i != 0:
                # reset all the vectors
                self.final_route_df = pd.DataFrame()
                self.chosen_idx = list()
                self.duration_vec = self.create_duration_vec()
                self.duration_vec_norm = None
                self.paid_attrac_vec = None
                self.availability_vec = None
                if len(self.chosen_idx) > 0:
                    self.last_idx = self.chosen_idx[-1]
                self.sum_duration = 0
                self.duration_paid_attrac = 0

                # create new rest instance with a new list of uuids to drop
                if rest_instance:
                    rest_instance = rest.Restaurants(rest_instance.df_rest, rest_instance.distances_matrix,
                                                     rest_instance.df_tags_weights, rest_instance.RESTAURANTS_TAGS_LIST,
                                                     self.all_days_restaurants_idx)
            # daily anchors
            if self.user_dates[i] in self.anchors.keys():
                daily_anchors = self.anchors[self.user_dates[i]]
            else:
                daily_anchors = None

            if rest_instance:
                daily_route = self.route_with_restaurants(rest_instance, daily_anchors)
                route_dict[i + 1] = daily_route
                self.all_days_restaurants_idx = list(set(self.all_days_restaurants_idx + list(
                    set(self.final_route_df["uuid"].values) & set(rest_instance.df_rest.index))))
                self.all_days_attractions_idx += list(
                    set(self.final_route_df["uuid"].values) & set(self.df["uuid"].values))
                print(f"added {len(daily_route) - 3} attractions")
                print("len chosen attractions:", len(self.all_days_attractions_idx))
                print("len chosen restaurants:", len(self.all_days_restaurants_idx))
            else:
                daily_route = self.build_route(daily_anchors=daily_anchors)

                for uuid in daily_route["uuid"].values:
                    similar_attraction_uuids = self.extract_similar_attractions(uuid)
                    idx = self.final_route_df[self.final_route_df["uuid"] == uuid].index[0]
                    self.final_route_df["additional_tickets_for_attraction"].iloc[idx] = \
                        df_uuid.loc[similar_attraction_uuids]["title"].values

                route_dict[self.user_dates[i]] = self.final_route_df
                self.all_days_attractions_idx += list(
                    set(self.final_route_df["uuid"].values) & set(self.df["uuid"].values))

        return route_dict

    def attraction_between_anchors(self, vector1, vector2):
        """
        input: 2 vectors with the attraction score according to each anchor
        output: the best attraction idx between the anchors
        """
        print("vector_score:", (vector1 + vector2))
        return (vector1 + vector2).sort_values().index[0]

    def select_middle_attrac(self, anchors, idx_to_drop=[]):
        """
         Args:
             anchors= {uuid: hour}

        Return:
            str.
         output: attraction idx between the anchors: (between 10 and 30)
        """
        ## select the attraction in the middle
        # reset the chosen_idx and update the vectors according to the first anchore and its chosen attractions
        idx_to_drop += anchors[0] + anchors[2]
        chosen_idx = anchors[0]
        self.similarity_vec = 0
        self.update_vectors(anchors[0])
        new_anchore1_vec = self.attractions_score_vec(idx_to_drop)

        # reset the chosen_idx and update the vectors according to the second anchore and its chosen attractions
        chosen_idx = anchors[2]
        self.similarity_vec = 0
        self.update_vectors(anchors[2])
        new_anchore2_vec = self.attractions_score_vec(idx_to_drop)

        # find the middle attraction according to both anchores
        middle_attraction_idx = self.attraction_between_anchors(new_anchore1_vec, new_anchore2_vec)
        # print("middle attraction", middle_attraction_idx)

        return middle_attraction_idx

    def even_attractions_between_anchors(self, idx_vec):  # np.array([0,10,20,30,40,50])
        """
        find the best 2 middle attractions according to both anchors (find the best "20, 30")
        """
        for i in range(5):
            print(f"itteration {i}")
            middle1_position = len(idx_vec) // 2 - 1  # 2
            middle2_position = len(idx_vec) // 2  # 3
            middle1 = idx_vec[middle1_position]  # 20
            middle2 = idx_vec[middle2_position]  # 30

            # find middle 1
            print("middle1:", middle1)
            middle1_new = self.select_middle_attrac(
                {0: idx_vec[:middle1_position], 2: idx_vec[middle2_position::][::-1]})
            print("middle1_new:", middle1_new)
            # update the new middle 1 in the list
            idx_vec[middle1_position] = middle1_new

            # find middle 2
            print("middle2:", middle2)
            middle2_new = self.select_middle_attrac(
                {0: idx_vec[:middle2_position], 2: idx_vec[middle2_position + 1::][::-1]})
            print("middle2:", middle2_new)
            # update the new middle 2 in the list
            idx_vec[middle2_position] = middle2_new

            if middle1 == middle1_new and middle2 == middle2_new:
                print("found the best middle attractions!")
                return idx_vec
        return idx_vec

    def select_attractions_between_anchors(self):
        """
        input: a dictionary with 2 items (anchors)
        output: a list with the anchors and the selected attractions between them
        """

        # for testing only!!
        # anchors = {self.anchors.keys_list[0]: self.anchors.position_list[0] , self.anchors.keys_list[0+1]: self.anchors.position_list[0+1] }
        # self.current_anchors = Anchors(anchors)
        # print(self.current_anchors.anchors)

        # number of attractions to select according to each anchore
        num_attractions_per_anchore = self.current_anchors.num_attrac_between(self.current_anchors.position_list[0],
                                                                              self.current_anchors.position_list[
                                                                                  1]) // 2
        print("num_attractions_per_anchore:", num_attractions_per_anchore)

        chosen_idx = list()
        # create a list with the anchors and their chosen attractions idx
        idx_to_drop = self.chosen_idx.copy() + self.anchors.uuids

        # first anchore:
        # insert the first anchore to chosen_idx
        print(self.current_anchors.keys_list[0])
        chosen_idx.append(self.current_anchors.keys_list[0])
        print(chosen_idx)

        # selecting attraction/s according to the first anchore
        chosen_idx = self.select_attractions_idx(chosen_idx, idx_to_drop)
        first_anchore_idx = chosen_idx.copy()
        print("chosen_idx:", chosen_idx)  # [10, 20]
        print("idx to drop:", idx_to_drop)

        # add the second anchore to the list
        idx_to_drop.append(self.current_anchors.keys_list[1])  # [10, 20, 50]

        # add chosen_idx the second anchore
        chosen_idx.append(self.current_anchors.keys_list[1])

        # reset self.similarity_vec (that we will not have the history value of the first anchore)
        # self.similarity_vec = 0

        # adding attractions according to the second anchore, drop the attractions that were already chosen by the first anchore
        attractions_anchore2 = self.select_attractions_idx(chosen_idx,
                                                           idx_to_drop)  # [10, 20, 50, 40]
        # chosen_idx += attractions_anchore2
        second_anchore_idx = chosen_idx[num_attractions_per_anchore + 1:]  # [50, 40]
        print("second_anchore_idx:", second_anchore_idx)
        print("chosen_idx:", chosen_idx)  # [10, 20, 50, 40]

        ### select the attraction in the middle
        # middle_attraction_idx = self.select_middle_attrac({0:first_anchore_idx, 2:second_anchore_idx})

        # join the indices to one list and reverse the second list so that the anchore will be the last item
        anchors_idx = first_anchore_idx + second_anchore_idx[::-1]  # [10, 20, 40, 50]
        print("anchors idx", anchors_idx)

        # no attractions between anchors
        num_attractions_between = self.current_anchors.num_attrac_between(self.current_anchors.position_list[0],
                                                                          self.current_anchors.position_list[1])
        if num_attractions_between == 0:
            chosen_idx = anchors_idx

        # even number of attractions between anchors
        elif num_attractions_between % 2 == 0:
            chosen_idx = self.even_attractions_between_anchors(anchors_idx)

        # odd number of attractions between anchors
        else:
            # idx_to_drop = chosen_idx.copy() + self.anchors.keys_list
            print("idx_to_drop:", idx_to_drop)
            ### select the attraction in the middle
            middle_attraction_idx = self.select_middle_attrac({0: first_anchore_idx, 2: second_anchore_idx},
                                                              idx_to_drop)

            # add the middle attraction to the idx list
            anchors_idx.insert(num_attractions_per_anchore + 1, middle_attraction_idx)
            chosen_idx = anchors_idx

        print("chosen attractions by both anchors", chosen_idx)
        return chosen_idx

    def attractions_before_anchore(self, chosen_idx):
        """
        select attractions idx before anchore
        """
        duration_before_anchore = self.anchors.duration_before()
        # Drop off the attractions that have already been selected
        idx_to_drop = chosen_idx
        # reverse chosen_idx in order to choose the "before attractions"
        chosen_idx = chosen_idx[::-1]
        self.select_attractions_idx(chosen_idx, idx_to_drop)
        # reverse again chosen_idx
        chosen_idx = chosen_idx[::-1]
        return chosen_idx

    def attractions_after_anchors(self, chosen_idx):
        """
        select attractions idx after anchore
        """
        num_attrac_to_select = self.anchors.num_attrac_after(self.tot_attractions_duration)
        # Drop off the attractions that have already been selected
        idx_to_drop = chosen_idx.copy()
        self.select_attractions_idx(chosen_idx, idx_to_drop)
        return chosen_idx

    def route_with_anchors(self, anchors_per_date: Dict):
        """
        select attractions for route with anchors
        """
        for anchore, hour in anchors_per_date.items():
            self.final_route_df = self.uuid_to_df([anchore], self.final_route_df, hour)
            ### select all attractions before the anchore (reversed)
            # drop the already selected attraction from the list of attractions (self.chosen_idx)
            uuid_to_drop = [anchore]
            self.update_sum_duration([anchore])
            self.update_paid_attrac_duration([anchore])
            start_route = 9
            start_anchore = hour
            duration = hour - start_route
            start_hour = self.final_route_df['start'].values[0] - duration
            self.select_attractions_idx(start_attractions=start_hour, end_attractions=start_anchore, chosen_uuid=[anchore],
                                        uuids_to_drop=self.anchors_uuids, reverse_order=True)

            # reverse self.final_route_df to be in ascending order
            self.final_route_df = self.final_route_df[::-1]
            ### select all attractions after the anchore
            chosen_uuid = list(self.final_route_df["uuid"].values)
            if 0 in chosen_uuid:
                chosen_uuid.remove(0)
            chosen_uuid += self.anchors_uuids
            end_anchore = self.final_route_df[self.final_route_df["uuid"] == anchore]["end"].values[0]
            self.select_attractions_idx(start_attractions=end_anchore, end_attractions=20, chosen_uuid=chosen_uuid,
                                        uuids_to_drop=chosen_uuid, reverse_order=False)
            self.chosen_idx = list(self.final_route_df["uuid"].values)
            if 0 in self.chosen_idx:
                self.chosen_idx.remove(0)
            return self.final_route_df

    def uuid_to_df(self, uuid, selected_attractions_df, start_hour=None, reverse=False):
        """
        extract the row of the chosen uuid from attractions df
        :param uuid:
        :return:
        """
        df_uuid = self.df.copy()
        df_uuid.set_index("uuid", drop=True, inplace=True)
        selected_attraction = df_uuid[["title", "hour", "inventory_supplier"]].loc[uuid]
        selected_attraction["start"] = None
        selected_attraction["end"] = None
        selected_attraction["additional_tickets_for_attraction"] = None
        selected_attraction.reset_index(inplace=True)
        selected_attractions_df = pd.concat([selected_attractions_df, selected_attraction], ignore_index=True)
        if len(selected_attractions_df) == 1:
            if start_hour:
                selected_attractions_df["start"].iloc[-1] = start_hour
                selected_attractions_df["end"].iloc[-1] = start_hour + selected_attractions_df.iloc[-1]["hour"]
            else:
                selected_attractions_df["start"] = 9.5
                selected_attractions_df["end"] = 9.5 + selected_attractions_df.iloc[-1]["hour"]
            col = "end"
        else:
            if not reverse:
                selected_attractions_df["start"].iloc[-1] = selected_attractions_df.iloc[-2]["end"] + 0.5
                selected_attractions_df["end"].iloc[-1] = selected_attractions_df["start"].iloc[-1] + \
                                                          selected_attractions_df["hour"].iloc[-1]
                col = "end"
            else:
                selected_attractions_df["end"].iloc[-1] = selected_attractions_df["start"].iloc[-2] - 0.5
                selected_attractions_df["start"].iloc[-1] = selected_attractions_df["end"].iloc[-1] - \
                                                            selected_attractions_df["hour"].iloc[-1]
                col = "start"

        # if instead of attraction we need to have lunch
        end = selected_attractions_df["end"].iloc[-1]

        if 13 <= selected_attractions_df[col].iloc[-1] < 16:
            if 0 not in selected_attractions_df["uuid"].values:
                if col == "start":  # reverse
                    restaurant_start = selected_attractions_df[col].iloc[-1] - 1
                else:
                    restaurant_start = selected_attractions_df[col].iloc[-1]

                selected_attractions_df = selected_attractions_df.append(
                    [{"uuid": 0, "title": 'Lunch time', "hour": 1, "start": restaurant_start,
                      "end": restaurant_start + 1, "additional_tickets_for_attraction": np.nan}],
                    ignore_index=True)

        return selected_attractions_df

    def build_route(self, daily_anchors=None):
        """
        return a dataframe of the selected route
        """
        if daily_anchors:
            self.route_with_anchors(daily_anchors)
            print("final attractions:", self.chosen_idx)
            return self.final_route_df[self.final_route_df["uuid"] != 0]
        else:
            self.route_without_anchors()
            print("final attractions:", self.chosen_idx)
            return self.final_route_df[self.final_route_df["uuid"] != 0]

    def route_with_restaurants(self, rest_instance, anchors_per_date=None):

        # create a dataframe of the selected attractions
        df_uuid = self.df.copy()
        df_uuid.set_index("uuid", drop=True, inplace=True)
        selected_attractions = self.build_route(anchors_per_date)

        # add optional tickets for same attraction
        for uuid in selected_attractions["uuid"].values:
            similar_attraction_uuids = self.extract_similar_attractions(uuid)
            idx = self.final_route_df[self.final_route_df["uuid"] == uuid].index[0]
            self.final_route_df["additional_tickets_for_attraction"].iloc[idx] = df_uuid.loc[similar_attraction_uuids][
                "title"].values

        # create a copy of the selected attractions indices
        route_uuid_list = self.final_route_df["uuid"].values
        rest_uuid_list = list()  # chosen uuids to drop

        rest_kind_dict = {'breakfast': 0, 'lunch': 1, 'dinner': 2}

        ## choose the first restaurant at the begining of the route
        rest_uuid = rest_instance.best_rest_uuid(
            rest_instance.rest_vec(route_uuid_list[0], rest_kind_dict['breakfast'], rest_uuid_list))
        rest_uuid_list.append(rest_uuid)
        # add the chosen restaurant to the route dataframe
        rest_title = rest_instance.df_rest.loc[rest_uuid]["title"]
        self.final_route_df = pd.DataFrame(
            np.insert(self.final_route_df.values, 0, values=[rest_uuid, rest_title, 1, np.nan, 8, 9, np.nan], axis=0))
        self.final_route_df.columns = ["uuid", "title", "hour", "inventory_supplier", "start", "end",
                                       "additional_tickets_for_attraction"]

        # choose lunch
        try:
            lunch_idx = self.final_route_df[self.final_route_df["uuid"] == 0].index[0]

            attrac_before = self.final_route_df.iloc[lunch_idx - 1]["uuid"]
            attrac_after = self.final_route_df.iloc[lunch_idx + 1]["uuid"]
            rest_uuid = rest_instance.best_rest_uuid(
                rest_instance.rest_between_attractions(attrac_before, attrac_after,
                                                       rest_uuid_list, rest_kind_dict['lunch']))
            rest_uuid_list.append(rest_uuid)
            # add the chosen restaurant to the route dataframe
            rest_title = rest_instance.df_rest.loc[rest_uuid]["title"]
            self.final_route_df["title"].iloc[lunch_idx] = rest_title
            self.final_route_df["uuid"].iloc[lunch_idx] = rest_uuid
        except:
            pass
        ## choose dinner
        rest_uuid = rest_instance.best_rest_uuid(
            rest_instance.rest_vec(route_uuid_list[-1], rest_kind_dict['dinner'], rest_uuid_list))
        rest_uuid_list.append(rest_uuid)

        # add the chosen restaurant to the route dataframe
        rest_title = rest_instance.df_rest.loc[rest_uuid]["title"]
        dinner_start = self.final_route_df["end"].iloc[-1] + 0.5
        self.final_route_df = self.final_route_df.append(
            {"title": rest_title, "uuid": rest_uuid, "hour": 1, "start": dinner_start, "end": dinner_start + 1.5,
             "additional_tickets_for_attraction": np.nan},
            ignore_index=True)

        return self.final_route_df

    def create_map_file(self, selected_attractions_dict, api_key, file_name, rest_df=None):
        rest_df.reset_index(inplace=True)
        if "index" in rest_df.columns:
            rest_df.rename(columns={"index": "uuid"}, inplace=True)
        # extract 'geolocation' from attractions df and from restaurant df
        for k, v in selected_attractions_dict.items():
            selected_attractions = v
            selected_attractions_rest_geo = selected_attractions.merge(rest_df[["uuid", "geolocation"]], how="inner")
            selected_attractions = selected_attractions.merge(self.df[["uuid", "geolocation"]], how="left")
            rest_uuids = selected_attractions_rest_geo["uuid"].values
            selected_attractions.set_index("uuid", inplace=True)
            selected_attractions["geolocation"].loc[rest_uuids] = selected_attractions_rest_geo["geolocation"].values

            # create 'lon' and 'lat' columns
            selected_attractions = selected_attractions[selected_attractions.index != 0]
            try:
                selected_attractions["lon"] = selected_attractions["geolocation"].apply(
                    lambda x: min([float(s) for s in re.findall(r'-?\d+\.?\d*', x)][-2:]))
                selected_attractions["lat"] = selected_attractions["geolocation"].apply(
                    lambda x: max([float(s) for s in re.findall(r'-?\d+\.?\d*', x)][-2:]))
            except TypeError:
                print("Some geolocations in the final route are missing!")
                continue
            # optional colors

            colors = ["y" for i in range(selected_attractions.shape[0])]

            latitude_list = selected_attractions["lat"]
            longitude_list = selected_attractions["lon"]

            gmap = gmplot.GoogleMapPlotter(latitude_list.mean(), longitude_list.mean(), 11)
            gmap.scatter(latitude_list, longitude_list, color=random.sample(colors, selected_attractions.shape[0]),
                         s=60,
                         ew=2,
                         marker=True,
                         symbol='+',
                         label=[i + 1 for i in range(selected_attractions.shape[0])])

            # polygon method Draw a polygon with
            # the help of coordinates
            gmap.polygon(latitude_list, longitude_list, color='cornflowerblue')
            gmap.apikey = api_key
            gmap.draw(f"day{k}_{file_name}")

    def test_route(self):
        # test if we have duplications
        assert len(self.chosen_idx) == len(set(self.chosen_idx)), "found duplicates!"

        # test the len of the route
        # assert len(
        #     self.chosen_idx) == self.tot_attractions_duration, "The length of the route is not equal to the one defined!"

        # test the position of each anchore in the selected route
        if self.anchors:
            for anchore in self.anchors.uuids:
                assert self.anchors.anchors[anchore] - 1 == self.chosen_idx.index(
                    anchore), "Anchors not in the right position!"

        print("The tests passed successfully!")


def main():
    with open('data_path.json') as f:
        data_path = json.load(f)

    # df = pd.read_csv(ATTRACTIONS_PATH)
    city = "ny"
    df = pd.read_csv(data_path["ATTRACTIONS_PATH"][city])

    # add same ticket similarity
    df = dp.data_preprocess(df)
    availability_df = pd.read_csv(data_path["AVAILABILITY_PATH"][city])

    df_distances_norm = pd.read_csv(data_path["DISTANCE_PATH"][city])
    df_distances_norm.set_index("uuid", drop=True, inplace=True)
    df_distances_norm.columns = df_distances_norm.index

    df_similarity_norm = pd.read_csv(data_path["SIMILARITY_PATH"][city])
    df_similarity_norm.set_index("uuid", drop=True, inplace=True)
    df_similarity_norm.columns = df_similarity_norm.index
    print(df_distances_norm.loc["63d92816-28ef-4a0f-9303-6796697ec6a8"]["e6a830a7-62d9-4616-8e0c-8791e201a63c"])
    print(df_similarity_norm.loc["63d92816-28ef-4a0f-9303-6796697ec6a8"]["e6a830a7-62d9-4616-8e0c-8791e201a63c"])
    # restaurants
    RESTAURANTS_TAGS_LIST = rest.RESTAURANTS_TAGS_LIST
    rest_tags_weights = pd.read_csv(data_path["REST_TAGS_WEIGHTS_PATH"])
    rest_df = pd.read_csv(data_path["REST_PATH"][city])
    rest_df.set_index("uuid", drop=True, inplace=True)
    rest_distances_norm = pd.read_csv(data_path["REST_DISTANCE_PATH"][city])
    rest_distances_norm.set_index("uuid", drop=True, inplace=True)
    rest_instance = rest.Restaurants(rest_df, rest_distances_norm, rest_tags_weights, RESTAURANTS_TAGS_LIST, [])
    print(df_similarity_norm.loc["bd3e862e-37cc-4564-bf66-7630827e6830"]["565e696f-4a4c-414b-afb4-70c97f094214"])
    print(df_distances_norm.loc["bd3e862e-37cc-4564-bf66-7630827e6830"]["565e696f-4a4c-414b-afb4-70c97f094214"])
    weight_dict = {"popular": 0, "distance": 8, "similarity": 0, "tags": 0}

    # user onboarding
    # chosen_tags = ["Architecture", "Culinary Experiences", "Shopping", "Art", "Urban Parks", "Museums"]
    chosen_tags = ["Museums", "Urban Parks", "Shows/Performance"]
    # user dates
    from_date = datetime.strptime("2022-12-15", "%Y-%m-%d")
    to_date = datetime.strptime("2022-12-17", "%Y-%m-%d")
    user_dates = [from_date + timedelta(days=i) for i in range((to_date - from_date).days + 1)]

    ATTRACTIONS_DURATION = 7
    # anchors = Anchors({"abdc2429-b0b3-4296-83ae-7c648baf564d": 16})
    #                    "96fe7ece-ef7d-4c1f-b7fa-ef6b1d5b12a0": 2,
    #                    "16149ccd-7b45-453f-981b-114cfb24f2de": 7})  # (idx: location in the route. starts at 1, not 0)

    # select formula weights
    # anchors = {user_dates[0]: {"b651ca92-23fd-460d-bcda-c7a274001592": 9.5},
    #            user_dates[1]: {"53c8be37-4023-4c27-a5ab-b309a92eeadb": 12}}

    new_route = RouteBulider(df, chosen_tags, df_similarity_norm, df_distances_norm, ATTRACTIONS_DURATION,
                             weight_dict, user_dates, availability_df, anchors={})

    all_days_route = new_route.create_full_route(rest_instance)
    api_key = 'AIzaSyCoqQ2Vu2yD99PqVlB6A6_8CyKHKSyJDyM'
    new_route.create_map_file(all_days_route, api_key, f"{city}_route.html", rest_df)
    return all_days_route


if __name__ == "__main__":

    route = main()
    for v in route.values():
        print(v[["title", "uuid"]])
        print(v["additional_tickets_for_attraction"])
        print("\n")
    # print(route)
