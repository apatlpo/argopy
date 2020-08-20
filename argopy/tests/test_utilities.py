import os
import io
import pytest
import unittest
import argopy
import xarray as xr
import numpy as np
import types
from argopy.utilities import (
    load_dict,
    mapp_dict,
    list_multiprofile_file_variables,
    isconnected,
    erddap_ds_exists,
    list_available_data_src,
    linear_interpolation_remap,
    Chunker,
    is_box,
    is_list_of_strings,
    is_list_of_integers
)
from argopy.errors import InvalidFetcherAccessPoint
from argopy import DataFetcher as ArgoDataFetcher

AVAILABLE_SOURCES = list_available_data_src()
CONNECTED = isconnected()


def test_invalid_dictionnary():
    with pytest.raises(ValueError):
        load_dict("invalid_dictionnary")


def test_invalid_dictionnary_key():
    d = load_dict("profilers")
    assert mapp_dict(d, "invalid_key") == "Unknown"


def test_list_multiprofile_file_variables():
    assert is_list_of_strings(list_multiprofile_file_variables())


def test_show_versions():
    f = io.StringIO()
    argopy.show_versions(file=f)
    assert "INSTALLED VERSIONS" in f.getvalue()


def test_isconnected():
    assert isinstance(isconnected(), bool)
    assert isconnected(host="http://dummyhost") is False


def test_erddap_ds_exists():
    assert isinstance(erddap_ds_exists(ds="ArgoFloats"), bool)
    assert erddap_ds_exists(ds="DummyDS") is False


@unittest.skipUnless("localftp" in AVAILABLE_SOURCES, "requires localftp data fetcher")
def test_clear_cache():
    ftproot, flist = argopy.tutorial.open_dataset("localftp")
    testcachedir = os.path.expanduser(os.path.join("~", ".argopytest_tmp"))
    with argopy.set_options(cachedir=testcachedir, local_ftp=ftproot):
        ArgoDataFetcher(src="localftp").profile(2902696, 12).to_xarray()
        argopy.clear_cache()
        assert os.path.isdir(testcachedir) is False


# We disable this test because the server has not responded over a week (May 29th)
# @unittest.skipUnless(CONNECTED, "open_etopo1 requires an internet connection")
# def test_open_etopo1():
#     try:
#         ds = open_etopo1([-80, -79, 20, 21], res='l')
#         assert isinstance(ds, xr.DataArray) is True
#     except requests.HTTPError:  # not our fault
#         pass


class test_linear_interpolation_remap(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def create_data(self):
        # create fake data to test interpolation:
        temp = np.random.rand(200, 100)
        pres = np.sort(
            np.floor(
                np.zeros([200, 100])
                + np.linspace(50, 950, 100)
                + np.random.randint(-5, 5, [200, 100])
            )
        )
        self.dsfake = xr.Dataset(
            {
                "TEMP": (["N_PROF", "N_LEVELS"], temp),
                "PRES": (["N_PROF", "N_LEVELS"], pres),
            },
            coords={
                "N_PROF": ("N_PROF", range(200)),
                "N_LEVELS": ("N_LEVELS", range(100)),
                "Z_LEVELS": ("Z_LEVELS", np.arange(100, 900, 20)),
            },
        )

    def test_interpolation(self):
        # Run it with success:
        dsi = linear_interpolation_remap(
            self.dsfake.PRES,
            self.dsfake["TEMP"],
            self.dsfake["Z_LEVELS"],
            z_dim="N_LEVELS",
            z_regridded_dim="Z_LEVELS",
        )
        assert "remapped" in dsi.dims

    def test_error_zdim(self):
        # Test error:
        # catches error from _regular_interp linked to z_dim
        with pytest.raises(RuntimeError):
            linear_interpolation_remap(
                self.dsfake.PRES,
                self.dsfake["TEMP"],
                self.dsfake["Z_LEVELS"],
                z_regridded_dim="Z_LEVELS",
            )

    def test_error_ds(self):
        # Test error:
        # catches error from linear_interpolation_remap linked to datatype
        with pytest.raises(ValueError):
            linear_interpolation_remap(
                self.dsfake.PRES,
                self.dsfake,
                self.dsfake["Z_LEVELS"],
                z_dim="N_LEVELS",
                z_regridded_dim="Z_LEVELS",
            )


class test_Chunker(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def create_data(self):
        self.WMO = [
            6902766,
            6902772,
            6902914,
            6902746,
            6902916,
            6902915,
            6902757,
            6902771,
        ]
        self.BOX3d = [0, 20, 40, 60, 0, 1000]
        self.BOX4d = [0, 20, 40, 60, 0, 1000, "2001-01", "2001-6"]

    def test_InvalidFetcherAccessPoint(self):
        with pytest.raises(InvalidFetcherAccessPoint):
            Chunker({"invalid": self.WMO})

    def test_chunk_wmo(self):
        C = Chunker({"wmo": self.WMO})
        assert all(
            [all(isinstance(x, int) for x in chunk) for chunk in C.fit_transform()]
        )

        C = Chunker({"wmo": self.WMO}, chunks="auto")
        assert all(
            [all(isinstance(x, int) for x in chunk) for chunk in C.fit_transform()]
        )

        C = Chunker({"wmo": self.WMO}, chunks={"wmo": 1})
        assert all(
            [all(isinstance(x, int) for x in chunk) for chunk in C.fit_transform()]
        )
        assert len(C.fit_transform()) == 1

        with pytest.raises(ValueError):
            Chunker({"wmo": self.WMO}, chunks=["wmo", 1])

        C = Chunker({"wmo": self.WMO})
        assert isinstance(C.this_chunker, types.FunctionType) or isinstance(
            C.this_chunker, types.MethodType
        )

    def test_chunk_box3d(self):
        C = Chunker({"box": self.BOX3d})
        assert all([is_box(chunk) for chunk in C.fit_transform()])

        C = Chunker({"box": self.BOX3d}, chunks="auto")
        assert all([is_box(chunk) for chunk in C.fit_transform()])

        C = Chunker({"box": self.BOX3d}, chunks={"lon": 12, "lat": 1, "dpt": 1})
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 12

        C = Chunker({"box": self.BOX3d}, chunks={"lon": 1, "lat": 12, "dpt": 1})
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 12

        C = Chunker({"box": self.BOX3d}, chunks={"lon": 1, "lat": 1, "dpt": 12})
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 12

        C = Chunker({"box": self.BOX3d}, chunks={"lon": 4, "lat": 2, "dpt": 1})
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2 * 4

        C = Chunker({"box": self.BOX3d}, chunks={"lon": 2, "lat": 3, "dpt": 4})
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2 * 3 * 4

        with pytest.raises(ValueError):
            Chunker({"box": self.BOX3d}, chunks=["lon", 1])

        C = Chunker({"box": self.BOX3d})
        assert isinstance(C.this_chunker, types.FunctionType) or isinstance(
            C.this_chunker, types.MethodType
        )

    def test_chunk_box4d(self):
        C = Chunker({"box": self.BOX4d})
        assert all([is_box(chunk) for chunk in C.fit_transform()])

        C = Chunker({"box": self.BOX4d}, chunks="auto")
        assert all([is_box(chunk) for chunk in C.fit_transform()])

        C = Chunker(
            {"box": self.BOX4d}, chunks={"lon": 2, "lat": 1, "dpt": 1, "time": 1}
        )
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2

        C = Chunker(
            {"box": self.BOX4d}, chunks={"lon": 1, "lat": 2, "dpt": 1, "time": 1}
        )
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2

        C = Chunker(
            {"box": self.BOX4d}, chunks={"lon": 1, "lat": 1, "dpt": 2, "time": 1}
        )
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2

        C = Chunker(
            {"box": self.BOX4d}, chunks={"lon": 1, "lat": 1, "dpt": 1, "time": 2}
        )
        assert all([is_box(chunk) for chunk in C.fit_transform()])
        assert len(C.fit_transform()) == 2

        with pytest.raises(ValueError):
            Chunker({"box": self.BOX4d}, chunks=["lon", 1])

        C = Chunker({"box": self.BOX4d})
        assert isinstance(C.this_chunker, types.FunctionType) or isinstance(
            C.this_chunker, types.MethodType
        )


class test_is_box(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def create_data(self):
        self.BOX3d = [0, 20, 40, 60, 0, 1000]
        self.BOX4d = [0, 20, 40, 60, 0, 1000, "2001-01", "2001-6"]

    def test_box_ok(self):
        assert is_box(self.BOX3d)
        assert is_box(self.BOX4d)

    def test_box_notok(self):
        for box in [[], list(range(0, 12))]:
            with pytest.raises(ValueError):
                is_box(box)
            with pytest.raises(ValueError):
                is_box(box, errors="raise")
            assert not is_box(box, errors="ignore")

    def test_box_invalid_num(self):
        for i in [0, 1, 2, 3, 4, 5]:
            box = self.BOX3d
            box[i] = "str"
            with pytest.raises(ValueError):
                is_box(box)
            with pytest.raises(ValueError):
                is_box(box, errors="raise")
            assert not is_box(box, errors="ignore")

    def test_box_invalid_range(self):
        for i in [0, 1, 2, 3, 4, 5]:
            box = self.BOX3d
            box[i] = -1000
            with pytest.raises(ValueError):
                is_box(box)
            with pytest.raises(ValueError):
                is_box(box, errors="raise")
            assert not is_box(box, errors="ignore")

    def test_box_invalid_str(self):
        for i in [6, 7]:
            box = self.BOX4d
            box[i] = "str"
            with pytest.raises(ValueError):
                is_box(box)
            with pytest.raises(ValueError):
                is_box(box, errors="raise")
            assert not is_box(box, errors="ignore")
