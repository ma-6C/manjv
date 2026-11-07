package core

import (
	"encoding/hex"
	"encoding/json"
	"testing"
)

func TestHongguoRequestSignatureReferenceVectors(t *testing.T) {
	content := []byte(`[
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000000",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 1,
    "hash": "7615ef25bcbbd61bf3dc691d8cdf92c3a757de278867b3d89f15a07add1337b1676bd7cb"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000001",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "dc91f2b02b9fecb5abb9c2d4481d189fe62d24a4"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000002",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "1bd0f3409a5a5873cbbfc3a006951eb697a46870"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000003",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 1,
    "hash": "6f3b084c0ae586b62c66e86ccf44c69fa757de278867b3d89f15a07add1337b16c12f973"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000004",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "eecb460869946cfa068de85450845bf4cffd2a96"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000005",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "3771f65c6ce3026a0d0fe4f48c740eeac746b5f4"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000006",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "7f0440cc81efe015ae99e6f0e742119457717b22"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000007",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "c6d33154b90c26a76bf9aa4c2a12847b3e8838c2"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000008",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 1,
    "hash": "522a4537c526d87e82b16dd03b92265da757de278867b3d89f15a07add1337b14c3f6ef2"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000009",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "fa4ba94e44df21c38ad05eff6b61460614b73104"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000010",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "a85e8975195fcc7a979e56420206013f9ca2c8d6"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000011",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 1,
    "hash": "5a41d14e65ebb7a4b87aff06cba60650a757de278867b3d89f15a07add1337b1ef438611"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000012",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "2d2c2d7a529809d99cfea2078f94fb1dfe9bd2b4"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000013",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "6cd4ddb640e1d03c80e0d038809cd472048ebcfd"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000014",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "73c24fd93e9dba5d9bc4a13fae2ba771dda387fb"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000015",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "3486422cc3b5a8b5987497e958d92d89b6b52aea"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000016",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 0,
    "hash": "26e870043cc4c83d2b122647f2350088e4290834"
  },
  {
    "query": "aid=8662&device_id=1234567890123456789&version_name=7.1.3.32&ts=1793989000&_rticket=1793989000017",
    "body": "{\"biz_param\":{\"video_platform\":1024},\"mixed_video_id_map\":{\"1004\":[\"7697475425370377241\"]}}",
    "timestamp": 1793989000,
    "branch": 2,
    "hash": "9fe56ee04eea4d7b3adf2f60fb00c3c316f9bc95"
  }
]`)
	var vectors []struct {
		Query     string
		Body      string
		Timestamp uint32
		Branch    int
		Hash      string
	}
	if err := json.Unmarshal(content, &vectors); err != nil {
		t.Fatal(err)
	}
	for i, v := range vectors {
		query := hgSM3Bytes([]byte(v.Query))
		body := hgMd5([]byte(v.Body))
		actual := hex.EncodeToString(hgHashF13(query, body, hgLe32(v.Timestamp), v.Timestamp))
		if actual != v.Hash || hgBranchOf(v.Query, []byte(v.Body), v.Timestamp) != v.Branch {
			t.Errorf("reference vector %d branch %d differs: %s != %s", i, v.Branch, actual, v.Hash)
		}
	}
}
