import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add project root to sys.path
sys.path.append(os.getcwd())

from stream.cert_manager import CertificateManager


class TestCertificateManager:
    @pytest.fixture
    def mock_path(self):
        with patch("stream.cert_manager.Path") as mock:
            yield mock

    @pytest.fixture
    def mock_rsa(self):
        with patch("stream.cert_manager.rsa") as mock:
            yield mock

    @pytest.fixture
    def mock_x509(self):
        with patch("stream.cert_manager.x509") as mock:
            yield mock

    @pytest.fixture
    def mock_serialization(self):
        with patch("stream.cert_manager.serialization") as mock:
            yield mock

    def test_init_creates_dir(self, mock_path):
        """Test certificate manager creates certificate directory on init."""
        mock_dir = MagicMock()
        mock_path.return_value = mock_dir

        # Setup exists to return True so we don't trigger generation in init
        mock_dir.__truediv__.return_value.exists.return_value = True

        # We also need to mock _load_ca_cert calls to open/load
        with (
            patch("builtins.open", mock_open(read_data=b"data")),
            patch("stream.cert_manager.serialization.load_pem_private_key"),
            patch("stream.cert_manager.x509.load_pem_x509_certificate"),
        ):
            CertificateManager("test_certs")

            mock_path.assert_called_with("test_certs")
            mock_dir.mkdir.assert_called_with(exist_ok=True)

    def test_init_generates_ca_if_missing(self, mock_path, mock_rsa, mock_x509):
        """Test CA certificate generation when missing on init."""
        mock_dir = MagicMock()
        mock_path.return_value = mock_dir

        # Setup exists to return False for CA cert
        ca_cert_path = MagicMock()
        ca_cert_path.exists.return_value = False

        # Setup side_effect for division to handle paths
        # CA paths return the mock that has exists=False
        mock_dir.__truediv__.return_value = ca_cert_path

        # Mock key generation
        mock_key = MagicMock()
        mock_rsa.generate_private_key.return_value = mock_key
        mock_key.private_bytes.return_value = b"private_key_bytes"
        mock_key.public_key.return_value = MagicMock()

        # Mock builder
        mock_builder = MagicMock()
        mock_x509.CertificateBuilder.return_value = mock_builder
        mock_builder.subject_name.return_value = mock_builder
        mock_builder.issuer_name.return_value = mock_builder
        mock_builder.public_key.return_value = mock_builder
        mock_builder.serial_number.return_value = mock_builder
        mock_builder.not_valid_before.return_value = mock_builder
        mock_builder.not_valid_after.return_value = mock_builder
        mock_builder.add_extension.return_value = mock_builder

        mock_cert = MagicMock()
        mock_builder.sign.return_value = mock_cert
        mock_cert.public_bytes.return_value = b"cert_bytes"

        with (
            patch("builtins.open", mock_open()) as mocked_file,
            patch("stream.cert_manager.serialization.load_pem_private_key"),
            patch("stream.cert_manager.x509.load_pem_x509_certificate"),
        ):
            CertificateManager("test_certs")

            # Check if generate_private_key was called
            mock_rsa.generate_private_key.assert_called_once()

            # Check if files were written (key and cert)
            # We expect multiple calls to open (write key, write cert, read key, read cert)
            assert mocked_file.call_count >= 2

    def test_get_domain_cert_existing(self, mock_path):
        """Test retrieving existing domain certificate from cache."""
        mock_dir = MagicMock()
        mock_path.return_value = mock_dir

        # Setup paths
        # We need specific behavior for different paths
        ca_path_mock = MagicMock()
        ca_path_mock.exists.return_value = True

        domain_path_mock = MagicMock()
        domain_path_mock.exists.return_value = True

        def truediv_side_effect(arg):
            # If we divide by domain.crt or domain.key, return domain_path_mock
            if "example.com" in str(arg):
                return domain_path_mock
            return ca_path_mock

        mock_dir.__truediv__.side_effect = truediv_side_effect

        with (
            patch("builtins.open", mock_open(read_data=b"data")),
            patch(
                "stream.cert_manager.serialization.load_pem_private_key"
            ) as mock_load_key,
            patch(
                "stream.cert_manager.x509.load_pem_x509_certificate"
            ) as mock_load_cert,
        ):
            mock_load_key.return_value = "mock_key"
            mock_load_cert.return_value = "mock_cert"

            manager = CertificateManager("test_certs")
            key, cert = manager.get_domain_cert("example.com")

            assert key == "mock_key"
            assert cert == "mock_cert"

    def test_get_domain_cert_generates_new(self, mock_path, mock_rsa, mock_x509):
        """Test generating new domain certificate when not cached."""
        mock_dir = MagicMock()
        mock_path.return_value = mock_dir

        # CA exists, domain does not
        ca_path_mock = MagicMock()
        ca_path_mock.exists.return_value = True

        domain_path_mock = MagicMock()
        domain_path_mock.exists.return_value = False

        def truediv_side_effect(arg):
            if "example.com" in str(arg):
                return domain_path_mock
            return ca_path_mock

        mock_dir.__truediv__.side_effect = truediv_side_effect

        # Mock key generation
        mock_key = MagicMock()
        mock_rsa.generate_private_key.return_value = mock_key
        mock_key.private_bytes.return_value = b"domain_private_key"
        mock_key.public_key.return_value = MagicMock()

        # Mock builder for domain cert
        mock_builder = MagicMock()
        mock_x509.CertificateBuilder.return_value = mock_builder
        mock_builder.subject_name.return_value = mock_builder
        mock_builder.issuer_name.return_value = mock_builder
        mock_builder.public_key.return_value = mock_builder
        mock_builder.serial_number.return_value = mock_builder
        mock_builder.not_valid_before.return_value = mock_builder
        mock_builder.not_valid_after.return_value = mock_builder
        mock_builder.add_extension.return_value = mock_builder

        mock_cert = MagicMock()
        mock_builder.sign.return_value = mock_cert
        mock_cert.public_bytes.return_value = b"domain_cert_bytes"

        # We need CA cert loaded to sign
        mock_ca_cert = MagicMock()

        with (
            patch("builtins.open", mock_open(read_data=b"ca_data")),
            patch("stream.cert_manager.serialization.load_pem_private_key"),
            patch(
                "stream.cert_manager.x509.load_pem_x509_certificate"
            ) as mock_load_cert,
        ):
            mock_load_cert.return_value = mock_ca_cert

            manager = CertificateManager("test_certs")

            # Call get_domain_cert
            key, cert = manager.get_domain_cert("example.com")

            # Verify generation
            # 1 call to generate_private_key (for domain, CA was loaded)
            assert mock_rsa.generate_private_key.call_count == 1

            assert key == mock_key
            assert cert == mock_cert
